from flask import Flask, request, render_template, redirect, make_response, url_for
import random
import string
import boto3
import os
from botocore.exceptions import NoCredentialsError
import html
from datetime import timedelta

s3 = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)

key = os.getenv('KEY')

BUCKET_NAME = os.getenv('AWS_S3_BUCKET_NAME')

def renameObject(old, new):
    
    s3.copy_object(
        Bucket=BUCKET_NAME,
        CopySource={'Bucket': BUCKET_NAME, 'Key': old},
        Key=new
    )

    s3.delete_object(
        Bucket=BUCKET_NAME,
        Key=old
    )

def listFiles():
    try:
        response = s3.list_objects_v2(Bucket=BUCKET_NAME)
        files = response.get('Contents', [])
        return files
    except NoCredentialsError:
        return []

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 3 * 1024 * 1024 


def create_paste(text):
    filename = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(6))

    s3.put_object(Bucket=BUCKET_NAME, Key=filename, Body=text)
    return filename

@app.route('/edit', methods=["GET", "POST"])
def edit():


    if request.method == "POST":
        cookie = request.cookies.get("key")
        if cookie == key:

            
            newText = html.escape(request.form.get('text'))
            file_name = request.form.get('file_name')
            s3.delete_object(Bucket=BUCKET_NAME, Key=file_name)
            s3.put_object(Bucket=BUCKET_NAME, Key=file_name, Body=newText)

            return redirect(f"/v?id={file_name}")
            
    elif request.method == "GET":
        cookie = request.cookies.get("key")
        if cookie == key:

            file_name = request.args.get('id')

            if not file_name:
                return "No file id provided!"

            response = s3.get_object(Bucket=BUCKET_NAME, Key=file_name)
            content = response['Body'].read().decode('utf-8')
            
            return render_template('edit.html', oldtext=content)




@app.route('/v')
def paste():
    file_name = request.args.get('id')
    
    if not file_name:
        return "Error: No file name provided", 400
    
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=file_name)
        content = response['Body'].read().decode('utf-8')
        processed_content = html.escape(content)
        return f"<pre style='font-family: mono, monospace; text-wrap: wrap; font-size: 12px; '>{processed_content}</pre>"
    except s3.exceptions.NoSuchKey:
        return "<pre style='font-family: mono, monospace; text-wrap: wrap; font-size: 12px; '>Error: Paste not found</pre>", 404
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/auth', methods=["GET", "POST"])
def auth():
    if request.method == "GET":
        pw = request.cookies.get('key')
        if pw == key:
            return redirect('/panel')
        elif pw != key:
            return render_template('auth.html')
        
    elif request.method == "POST":
        pw = request.form.get('key')
        if pw == key:
            resp = make_response(redirect('/panel'))
            resp.set_cookie('key', pw, max_age=timedelta(hours=12))

            return resp
        else:
            return render_template("auth.html", error = "Incorrect key.")

@app.route('/logout', methods=["GET"])
def logout():
    if request.method == "GET":
        log_out = make_response(redirect('/auth'))
        log_out.set_cookie('key', '', expires=0)
        
        return log_out
    
@app.route('/panel')
def panel():
    cookie = request.cookies.get('key')
    if cookie == key:
        showFiles = listFiles()
        return render_template('panel.html', files=showFiles)
    else:
        return redirect('/auth')


@app.route('/delete', methods=["POST"])
def delete():
    if request.method == "POST":
        cookie = request.cookies.get('key')
        if cookie == key:
            file = request.form.get('toDelete')
            s3.delete_object(Bucket=BUCKET_NAME, Key=file)
            return redirect('/panel')
        else:
            return redirect('/auth')

@app.route('/manage')
def manage():
    cookie = request.cookies.get('key')
    if cookie == key:
        if request.args.get('id') == None:
            return "Error: no file id provided! Please try again."
        else:
            file_key = request.args.get('id')
            return render_template('manage.html', file_key=file_key)
    else:
            return redirect('/auth')


@app.route('/rename', methods=["POST"])
def rename():
    cookie = request.cookies.get('key')
    if cookie == key:
        oldKey = request.form.get('oldKey')
        newKey = request.form.get('newKey')
        renameObject(oldKey, newKey)
        return redirect('/panel')
    else:
        return redirect('/auth')
    


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/submit', methods=['POST'])
def submit():
    text = request.form.get('text')
    
    return redirect(f"/v?id={create_paste(text)}")
    

@app.errorhandler(413)
def request_entity_too_large(error):
    return "Error: File too large. Maximum allowed size is 5MB.", 413


if __name__ == '__main__':
    app.run(debug=True, port="8080")
