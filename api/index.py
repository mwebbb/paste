from flask import Flask, request, render_template
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

def create_paste(text):
    filename = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(5))

    s3.put_object(Bucket=BUCKET_NAME, Key=filename, Body=text)
    return filename


    
@app.route('/paste')
def paste():
    file_name = request.args.get('id')
    response = s3.get_object(Bucket=BUCKET_NAME, Key=file_name)
    content = response['Body'].read().decode('utf-8')
    return content


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/submit', methods=['POST'])
def submit():
    text = request.form.get('text')
    
    
    return f"Paste submitted\nUrl: https://paste2-three.vercel.app/paste?{create_paste(text)}"


if __name__ == '__main__':
    app.run(debug=True)