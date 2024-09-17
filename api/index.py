from flask import Flask, request, render_template
import random 


app = Flask(__name__)

def create_paste(text):
    return hi
    


@app.route('/')
def home():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    text = request.form.get('text')
    
    
    return f"Paste submitted"


if __name__ == '__main__':
    app.run(debug=True)

