from flask import Flask, request, render_template, redirect
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

BUCKET_NAME = os.getenv('AWS_S3_BUCKET_NAME')


app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 


def create_paste(text):
    filename = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(5))

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
        
        return f"<pre style='font-family: monospace; text-wrap: wrap; font-size: 115%;'>{content}</pre>"
    except s3.exceptions.NoSuchKey:
        return "Error: Paste not found", 404
    except Exception as e:
        return f"Error: {str(e)}", 500



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
    app.run(debug=True)