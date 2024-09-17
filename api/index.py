from flask import Flask, request, render_template
import random
import string

app = Flask(__name__)

def create_paste(text):
    filename = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(5))

    file = open(f"/pastes/{filename}", "w")
    file.write(text)
    return filename

    
@app.route('/paste')
def paste():
    file_name = request.args.get('id')
    return open(file_name)
    


@app.route('/')
def home():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    text = request.form.get('text')
    
    
    return f"Paste submitted\nUrl: https://paste2-three.vercel.app/paste?{create_paste(text)}"


if __name__ == '__main__':
    app.run(debug=True)

