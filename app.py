from flask import Flask
from flask import render_template, request, redirect
import stripe
import smtplib

app = Flask(__name__)
@app.route('/liked')
def liked_items():
    return render_template('liked.html')

@app.route("/")
def home():
    return render_template("index.HTML")
if __name__=="__main__":
    app.run(debug=True, port = 5001)