from __future__ import unicode_literals
import json
import contextlib, io
import os
import subprocess
from queue import Queue
from bottle import route, run, Bottle, request, static_file
from threading import Thread
import youtube_dl
from pathlib import Path
from collections import ChainMap
from youtube_dl_logdb import JobsDB, Job

app = Bottle()

class QueueAction:
    DOWNLOAD = 1
    PURGE_LOGS = 2


app_defaults = {
    'YDL_FORMAT': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
    'YDL_EXTRACT_AUDIO_FORMAT': None,
    'YDL_EXTRACT_AUDIO_QUALITY': '192',
    'YDL_RECODE_VIDEO_FORMAT': None,
    'YDL_OUTPUT_TEMPLATE': '/youtube-dl/%(title)s [%(id)s].%(ext)s',
    'YDL_OUTPUT_TEMPLATE_PLAYLIST': '/youtube-dl/%(playlist_title)s/%(title)s [%(id)s].%(ext)s',
    'YDL_ARCHIVE_FILE': None,
    'YDL_SERVER_HOST': '0.0.0.0',
    'YDL_SERVER_PORT': 8080,
    'YDL_CACHE_DIR': '/youtube-dl/.cache',
    'YDL_DB_PATH': '/youtube-dl/.ydl-metadata.db',
}


@app.route('/')
def front_index():
    return static_file('index.html', root='./')


@app.route('/logs')
def front_logs():
    return static_file('logs.html', root='./')


@app.route('/static/:filename#.*#')
def server_static(filename):
    return static_file(filename, root='./static')


@app.route('/api/downloads/count', method='GET')
def api_queue_size():
    return {"success": True, "size": len(list(dl_q.queue))}


@app.route('/api/downloads', method='GET')
def api_logs():
    db = JobsDB(app_defaults['YDL_DB_PATH'], readonly=True)
    return json.dumps(db.get_all())

@app.route('/api/downloads', method='DELETE')
def api_logs_purge():
    dl_q.put((QueueAction.PURGE_LOGS, None))
    return {"success": True}


@app.route('/api/downloads', method='POST')
def api_queue_download():
    url = request.forms.get("url")
    options = {
        'format': request.forms.get("format")
    }

    if not url:
        return {"success": False, "error": "'url' query parameter omitted"}

    dl_q.put((QueueAction.DOWNLOAD, (url, options)))
    print("Added url " + url + " to the download queue")
    return {"success": True, "url": url, "options": options}

@app.route("/youtube-dl/update", method="GET")
def ydl_update():
    command = ["pip", "install", "--no-cache-dir", "--upgrade", "youtube-dl"]
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    output, error = proc.communicate()
    return {
        "output": output.decode('ascii'),
        "error":  error.decode('ascii')
    }

def dl_worker():
    db = JobsDB(app_defaults['YDL_DB_PATH'], readonly=False)
    while not done:
        action, extras = dl_q.get()
        if action == QueueAction.DOWNLOAD:
            url, options = extras
            job = Job(url, 0, "")
            db.insert_job(job)
            try:
                job.log = Job.clean_logs(download(url, options))
                job.status = 1
            except Exception as e:
                job.status = 2
                job.log += str(e)
                print("Exception during download task:\n" + str(e))
            db.update_job(job)
        elif action == QueueAction.PURGE_LOGS:
            db.purge_jobs()
        dl_q.task_done()


def get_ydl_options(request_options):
    request_vars = {
        'YDL_EXTRACT_AUDIO_FORMAT': None,
        'YDL_RECODE_VIDEO_FORMAT': None,
    }

    requested_format = request_options.get('format', 'bestvideo')

    if requested_format in ['aac', 'flac', 'mp3', 'm4a', 'opus', 'vorbis', 'wav']:
        request_vars['YDL_EXTRACT_AUDIO_FORMAT'] = requested_format
    elif requested_format == 'bestaudio':
        request_vars['YDL_EXTRACT_AUDIO_FORMAT'] = 'best'
    elif requested_format in ['mp4', 'flv', 'webm', 'ogg', 'mkv', 'avi']:
        request_vars['YDL_RECODE_VIDEO_FORMAT'] = requested_format

    ydl_vars = ChainMap(request_vars, os.environ, app_defaults)

    postprocessors = []

    if(ydl_vars['YDL_EXTRACT_AUDIO_FORMAT']):
        postprocessors.append({
            'key': 'FFmpegExtractAudio',
            'preferredcodec': ydl_vars['YDL_EXTRACT_AUDIO_FORMAT'],
            'preferredquality': ydl_vars['YDL_EXTRACT_AUDIO_QUALITY'],
        })

    if(ydl_vars['YDL_RECODE_VIDEO_FORMAT']):
        postprocessors.append({
            'key': 'FFmpegVideoConvertor',
            'preferedformat': ydl_vars['YDL_RECODE_VIDEO_FORMAT'],
        })

    return {
        'format': ydl_vars['YDL_FORMAT'],
        'postprocessors': postprocessors,
        'outtmpl': ydl_vars['YDL_OUTPUT_TEMPLATE'],
        'download_archive': ydl_vars['YDL_ARCHIVE_FILE'],
        'cachedir': ydl_vars['YDL_CACHE_DIR']
    }


def download(url, request_options):
    with youtube_dl.YoutubeDL(get_ydl_options(request_options)) as ydl:
        ydl.params['extract_flat']= 'in_playlist'
        info = ydl.extract_info(url, download=False)
        if '_type' in info and info['_type'] == 'playlist' \
                and 'YDL_OUTPUT_TEMPLATE_PLAYLIST' in app_defaults:
            ydl.params['outtmpl'] = app_defaults['YDL_OUTPUT_TEMPLATE_PLAYLIST']
        ydl.params['extract_flat']= False

        # Swap out sys.stdout as ydl's output so we can capture it
        ydl._screen_file = io.StringIO()
        ydl.download([url])
        return ydl._screen_file.getvalue()


dl_q = Queue()
done = False
dl_thread = Thread(target=dl_worker)
dl_thread.start()

print("Updating youtube-dl to the newest version")
updateResult = ydl_update()
print(updateResult["output"])
print(updateResult["error"])

print("Started download thread")

app_vars = ChainMap(os.environ, app_defaults)

app.run(host=app_vars['YDL_SERVER_HOST'], port=app_vars['YDL_SERVER_PORT'], debug=True)
done = True
dl_thread.join()
