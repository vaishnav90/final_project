from flask import Flask, render_template, request, redirect, url_for, flash
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from pymongo import MongoClient
from bson.objectid import ObjectId

app = Flask(__name__)
app.secret_key = '12345'  # key

# MongoDB Configuration
client = MongoClient('mongodb+srv://AsherB:3Nqgw4GgXKUe23i@cluster0.clkkf3n.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')  # MongoDB URI
db = client['ourapp']  # Database name
users_collection = db['logininfo']  # Collection name

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, user_id, username, email):
        self.id = user_id
        self.username = username
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    user_data = users_collection.find_one({'_id': ObjectId(user_id)})
    if user_data:
        return User(str(user_data['_id']), user_data['username'], user_data['email'])
    return None

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')

        # Check if user already exists
        if users_collection.find_one({'email': email}):
            flash('Email already registered. Please log in.', 'danger')
            return redirect(url_for('login'))

        # Create new user
        new_user = {
            'username': username,
            'email': email,
            'password': password
        }
        users_collection.insert_one(new_user)
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user_data = users_collection.find_one({'email': email})

        if user_data and bcrypt.check_password_hash(user_data['password'], password):
            user = User(str(user_data['_id']), user_data['username'], user_data['email'])
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password. Please try again.', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/liked')
@login_required
def liked_items():
    return render_template('liked.html')

@app.route('/howitworks')
def how_it_works():
    return render_template('howitworks.html')

if __name__ == "__main__":
    app.run(debug=True, port=5001)