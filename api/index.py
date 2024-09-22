from flask import Flask, request, render_template, redirect, make_response
import random
import string
import boto3
import os
from botocore.exceptions import NoCredentialsError


s3 = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)

key = os.getenv('KEY')

BUCKET_NAME = os.getenv('AWS_S3_BUCKET_NAME')


def listFiles():
    try:
        response = s3.list_objects_v2(Bucket=BUCKET_NAME)
        files = response.get('Contents', [])
        return files
    except NoCredentialsError:
        return []


app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 


def create_paste(text):
    filename = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(6))

    s3.put_object(Bucket=BUCKET_NAME, Key=filename, Body=text)
    return filename


@app.route('/paste')
def paste():
    file_name = request.args.get('id')
    
    if not file_name:
        return "Error: No file name provided", 400
    
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=file_name)
        content = response['Body'].read().decode('utf-8')
        
        return f"<pre style='font-family: mono; text-wrap: wrap; font-size: 90%; '>{content}</pre>"
    except s3.exceptions.NoSuchKey:
        return "Error: Paste not found", 404
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route('/login', methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template('login.html')
    elif request.method == "POST":
        pw = request.form.get('key')
        if pw == key:
            resp = make_response(redirect('/dashboard'))
            resp.set_cookie('key', pw)

            return resp
        else:
            return render_template("login.html", error = "invalid key")

    
@app.route('/dashboard')
def dashboard():
    cookie = request.cookies.get('key')
    if cookie == key:
        showFiles = listFiles()
        return render_template('dashboard.html', files=showFiles)
    else:
        return "wrong key"


@app.route('/delete', methods=["POST"])
def delete():
    if request.method == "POST":
        cookie = request.cookies.get('key')
        if cookie == key:
            file = request.form.get('toDelete')
            s3.delete_object(Bucket=BUCKET_NAME, Key=file)
            return redirect('/dashboard')
        else:
            return "you are not logged in"





@app.route('/')
def home():
    return render_template('index.html')


@app.route('/submit', methods=['POST'])
def submit():
    text = request.form.get('text')
    
    return redirect(f"/paste?id={create_paste(text)}")
    

@app.errorhandler(413)
def request_entity_too_large(error):
    return "Error: File too large. Maximum allowed size is 5MB.", 413


if __name__ == '__main__':
    app.run(debug=True, port="8080")