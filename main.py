from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime, timezone
import os
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
import smtplib
from flask import send_file
from io import BytesIO
from bson import ObjectId
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this to a secure secret key
socketio = SocketIO(app, cors_allowed_origins="*")

client = MongoClient('mongodb+srv://vaishnavanand:vannd0108@cluster0.clkkf3n.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
db = client['rethread']

users_collection = db['users']
listings_collection = db['listings']
messages_collection = db['messages']
transactions_collection = db['transactions']
reviews_collection = db['reviews']
saved_items_collection = db['saved_items']
categories_collection = db['categories']
neighborhoods_collection = db['neighborhoods']
images_collection = db['images']
offers_collection = db['offers']
flags_collection = db['flags']

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'vaishnavanand90@gmail.com'
app.config['MAIL_PASSWORD'] = 'your-app-password'  # You'll need to replace this with an App Password from Google Account settings
app.config['MAIL_DEFAULT_SENDER'] = 'vaishnavanand90@gmail.com'

messages_collection.create_index([('participants', 1)])
messages_collection.create_index([('listing_id', 1)])
mail = Mail(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.username = user_data['username']
        self.email = user_data['email']
        self.user_data = user_data

@login_manager.user_loader
def load_user(user_id):
    user_data = users_collection.find_one({'_id': ObjectId(user_id)})
    if user_data:
        return User(user_data)
    return None

def initialize_categories():
    """Initialize default categories if none exist"""
    existing_categories = categories_collection.count_documents({})
    if existing_categories == 0:
        default_categories = [
            {'name': 'womens', 'display_name': 'Women\'s Clothing', 'item_count': 0},
            {'name': 'mens', 'display_name': 'Men\'s Clothing', 'item_count': 0},
            {'name': 'childrens', 'display_name': 'Children\'s Clothing', 'item_count': 0},
            {'name': 'shoes', 'display_name': 'Shoes', 'item_count': 0},
            {'name': 'accessories', 'display_name': 'Accessories', 'item_count': 0},
            {'name': 'activewear', 'display_name': 'Activewear', 'item_count': 0},
            {'name': 'formal', 'display_name': 'Formal Wear', 'item_count': 0}
        ]
        categories_collection.insert_many(default_categories)

def initialize_neighborhoods():
    """Initialize default neighborhoods if none exist"""
    existing_neighborhoods = neighborhoods_collection.count_documents({})
    if existing_neighborhoods == 0:
        default_neighborhoods = [
            {'name': 'sanramon-valley', 'display_name': 'San Ramon Valley'},
            {'name': 'danville-downtown', 'display_name': 'Downtown Danville'},
            {'name': 'windemere', 'display_name': 'Windemere'},
            {'name': 'dougherty-valley', 'display_name': 'Dougherty Valley'},
            {'name': 'blackhawk', 'display_name': 'Blackhawk'},
            {'name': 'twin-creeks', 'display_name': 'Twin Creeks'},
            {'name': 'crow-canyon', 'display_name': 'Crow Canyon'}
        ]
        neighborhoods_collection.insert_many(default_neighborhoods)

# Initialize default data
initialize_categories()
initialize_neighborhoods()

@app.route('/')
def home():
    user_school = None
    if current_user.is_authenticated:
        user_school = current_user.user_data.get('profile', {}).get('school', None)

    # Filter by school if user is logged in and has a school set
    school_filter = {}
    if user_school:
        school_filter['profile.school'] = user_school

    # Get featured listings
    featured_listings = list(listings_collection.find({
        'status': 'available',
        'is_featured': True,
        **school_filter
    }).sort('created_at', -1).limit(8))

    # Get liked listings for the current user
    liked_listings = set()
    if current_user.is_authenticated:
        saved_items = saved_items_collection.find({'user_id': ObjectId(current_user.id)})
        liked_listings = {str(item['listing_id']) for item in saved_items}

    # Get popular categories with item counts
    pipeline = [
        {'$match': {'status': 'available', **school_filter}},
        {'$group': {'_id': '$category', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 4}
    ]
    
    category_counts = list(listings_collection.aggregate(pipeline))
    popular_categories = []
    
    for cat in category_counts:
        category_doc = categories_collection.find_one({'name': cat['_id']})
        if category_doc:
            category_doc['item_count'] = cat['count']
            popular_categories.append(category_doc)
    
    # If no categories with listings, get default categories
    if not popular_categories:
        popular_categories = list(categories_collection.find().limit(4))
    
    return render_template('index.html',
                         featured_listings=featured_listings,
                         liked_listings=liked_listings,
                         popular_categories=popular_categories)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        school = request.form['school']
        
        # Check if user already exists
        if users_collection.find_one({'email': email}):
            flash('Email already registered. Please log in.', 'danger')
            return redirect(url_for('login'))
        
        if users_collection.find_one({'username': username}):
            flash('Username already taken. Please choose another.', 'danger')
            return redirect(url_for('signup'))
        
        # Hash password
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # Create new user
        new_user = {
            'username': username,
            'email': email,
            'password': hashed_password,
            'profile': {
                'first_name': '',
                'last_name': '',
                'avatar': '/static/profile_images/vaishnav_pic.png' if email == 'vaishnavanand90@gmail.com' else '',
                'bio': '',
                'school': school,
                'neighborhood': '',
                'joined_date': datetime.utcnow(),
                'last_active': datetime.utcnow()
            },
            'verification': {
                'is_verified': False,
                'method': 'email'
            },
            'preferences': {
                'notifications': {
                    'messages': True,
                    'listing_updates': True,
                    'promotions': False
                }
            },
            'stats': {
                'listings_count': 0,
                'sold_count': 0,
                'rating': 0,
                'review_count': 0
            },
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        result = users_collection.insert_one(new_user)
        user_id = result.inserted_id
        
        # Log in the new user
        user_data = users_collection.find_one({'_id': user_id})
        user = User(user_data)
        login_user(user)
        
        flash('Account created successfully! Welcome to our community!', 'success')
        return redirect(url_for('home'))
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user_data = users_collection.find_one({'email': email})
        
        if user_data and bcrypt.check_password_hash(user_data['password'], password):
            user = User(user_data)
            login_user(user)
            
            # Update last active time
            users_collection.update_one(
                {'_id': ObjectId(user.id)},
                {'$set': {'profile.last_active': datetime.utcnow()}}
            )
            
            flash('Welcome back!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('Invalid email or password. Please try again.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('home'))

@app.route('/listings')
def listings():
    # Get current user's school
    user_school = None
    if current_user.is_authenticated:
        user_school = current_user.user_data.get('profile', {}).get('school', None)
    
    if not user_school:
        flash('Your profile does not have a school set. Please update your profile before listing an item.', 'danger')
        return redirect(url_for('profile'))

    # Get filter parameters from request
    neighborhood = request.args.get('neighborhood', 'all')
    category = request.args.get('category', '')
    price_min = float(request.args.get('min_price')) if request.args.get('min_price') else None
    price_max = float(request.args.get('max_price')) if request.args.get('max_price') else None
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'newest')

    # Build query with school filter
    query = {'status': 'available', 'profile.school': user_school}
    
    if neighborhood != 'all':
        query['neighborhood'] = neighborhood
    
    if category:
        query['category'] = category
    
    if price_min is not None:
        query.setdefault('price', {})['$gte'] = price_min
    
    if price_max is not None:
        query.setdefault('price', {})['$lte'] = price_max
    
    if search:
        query['$or'] = [
            {'title': {'$regex': search, '$options': 'i'}},
            {'description': {'$regex': search, '$options': 'i'}}
        ]
    
    # Determine sort order
    sort_options = {
        'newest': ('created_at', -1),
        'price_low': ('price', 1),
        'price_high': ('price', -1)
    }
    sort_field, sort_direction = sort_options.get(sort, ('created_at', -1))
    
    # Get listings and ensure created_at has timezone info
    listings = list(listings_collection.find(query).sort(sort_field, sort_direction))
    for listing in listings:
        if 'created_at' in listing and listing['created_at'].tzinfo is None:
            listing['created_at'] = listing['created_at'].replace(tzinfo=timezone.utc)
    
    # Get filter options
    neighborhoods = list(neighborhoods_collection.find())
    categories = list(categories_collection.find())
    
    return render_template('listings.html',
                         listings=listings,
                         neighborhoods=neighborhoods,
                         categories=categories,
                         selected_neighborhood=neighborhood,
                         selected_category=category,
                         search_query=search,
                         price_min=price_min,
                         price_max=price_max,
                         current_sort=sort)

@app.route('/listings/<listing_id>')
def listing_detail(listing_id):
    try:
        listing = listings_collection.find_one({'_id': ObjectId(listing_id)})
        if not listing:
            flash('Listing not found.', 'danger')
            return redirect(url_for('home'))
        
        # Get seller information
        seller = users_collection.find_one({'_id': ObjectId(listing['seller_id'])})
        
        # Check if current user has saved this listing
        is_saved = False
        if current_user.is_authenticated:
            is_saved = saved_items_collection.find_one({
                'user_id': current_user.id,
                'listing_id': listing_id
            }) is not None
        
        # Increment view count
        listings_collection.update_one(
            {'_id': ObjectId(listing_id)},
            {'$inc': {'views': 1}}
        )
        
        return render_template('listing_detail.html', 
                             listing=listing, 
                             seller=seller,
                             is_saved=is_saved)
    except:
        flash('Invalid listing ID.', 'danger')
        return redirect(url_for('home'))

@app.route('/sell', methods=['GET', 'POST'])
@login_required
def sell():
    if request.method == 'POST':
        image_ids = []
        if 'images' in request.files:
            files = request.files.getlist('images')
            for file in files:
                if file and allowed_file(file.filename):
                    image_doc = {
                        'filename': secure_filename(file.filename),
                        'content_type': file.content_type,
                        'data': file.read(),
                        'uploaded_by': str(current_user.id),
                        'uploaded_at': datetime.utcnow()
                    }
                    result = images_collection.insert_one(image_doc)
                    image_ids.append(str(result.inserted_id))
        
        # Get the user's school from their profile
        user_school = current_user.user_data.get('profile', {}).get('school', None)
        
        new_listing = {
            'title': request.form['title'],
            'description': request.form['description'],
            'price': float(request.form['price']),
            'category': request.form['category'],
            'size': request.form['size'],
            'condition': request.form['condition'],
            'neighborhood': request.form['neighborhood'],
            'images': image_ids,
            'status': 'available',
            'seller_id': str(current_user.id),
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'views': 0,
            'saves': 0,
            'profile': {
                'school': user_school
            }
        }
        
        listings_collection.insert_one(new_listing)
        flash('Your item has been listed successfully!', 'success')
        return redirect(url_for('home'))
    
    categories = list(categories_collection.find())
    neighborhoods = list(neighborhoods_collection.find())
    return render_template('sell.html', categories=categories, neighborhoods=neighborhoods)

# Route to serve images from MongoDB
@app.route('/image/<image_id>')
def get_image(image_id):
    image = images_collection.find_one({'_id': ObjectId(image_id)})
    if image:
        return send_file(BytesIO(image['data']), mimetype=image['content_type'])
    else:
        return "Image not found", 404

@app.route('/liked')
@login_required
def liked_items():
    # Get user's saved items
    saved_items = list(saved_items_collection.find({'user_id': current_user.id}))
    listing_ids = [ObjectId(item['listing_id']) for item in saved_items]
    liked_listings = list(listings_collection.find({'_id': {'$in': listing_ids}}))
    
    return render_template('liked.html', listings=liked_listings)

@app.route('/messages')
@login_required
def messages():
    try:
        # Get all conversations
        conversations = list(messages_collection.find({
            'participants': current_user.id
        }).sort('last_message', -1))
        
        conversations_data = []
        for conv in conversations:
            # Get other user
            other_user_id = next(id for id in conv['participants'] if id != current_user.id)
            other_user = users_collection.find_one({'_id': ObjectId(other_user_id)})
            
            # Get listing if it exists
            listing = None
            if 'listing_id' in conv:
                listing = listings_collection.find_one({'_id': ObjectId(conv['listing_id'])})
            
            conversations_data.append({
                'conversation': conv,
                'other_user': other_user,
                'listing': listing
            })
        
        return render_template('messages.html', conversations=conversations_data)
    except Exception as e:
        print(f"Error loading messages: {str(e)}")
        flash('Error loading messages. Please try again.', 'danger')
        return redirect(url_for('home'))

@app.route('/conversation/<conversation_id>')
@login_required
def conversation(conversation_id):
    try:
        # Get conversation
        conversation = messages_collection.find_one({'_id': ObjectId(conversation_id)})
        if not conversation:
            flash('Conversation not found.', 'danger')
            return redirect(url_for('messages'))
        
        # Check if user is part of conversation
        if current_user.id not in conversation['participants']:
            flash('You do not have access to this conversation.', 'danger')
            return redirect(url_for('messages'))
        
        # Get other user
        other_user_id = next(id for id in conversation['participants'] if id != current_user.id)
        other_user = users_collection.find_one({'_id': ObjectId(other_user_id)})
        
        # Get listing if it exists
        listing = None
        latest_offer = None
        if 'listing_id' in conversation:
            listing = listings_collection.find_one({'_id': ObjectId(conversation['listing_id'])})
            
            # Get latest offer for this listing between these users
            latest_offer = offers_collection.find_one({
                'listing_id': str(listing['_id']),
                'buyer_id': other_user_id if listing['seller_id'] == current_user.id else current_user.id,
                'status': 'pending'  # Only get pending offers
            }, sort=[('created_at', -1)])  # Get the most recent offer
        
        # Get all conversations for sidebar
        all_conversations = list(messages_collection.find({
            'participants': current_user.id
        }).sort('last_message', -1))
        
        conversations_data = []
        for conv in all_conversations:
            # Get other user
            other_id = next(id for id in conv['participants'] if id != current_user.id)
            other = users_collection.find_one({'_id': ObjectId(other_id)})
            
            # Get listing if it exists
            conv_listing = None
            if 'listing_id' in conv:
                conv_listing = listings_collection.find_one({'_id': ObjectId(conv['listing_id'])})
            
            conversations_data.append({
                'conversation': conv,
                'other_user': other,
                'listing': conv_listing
            })
        
        return render_template('messages.html',
                             conversation=conversation,
                             other_user=other_user,
                             listing=listing,
                             latest_offer=latest_offer,
                             conversations=conversations_data)
    except Exception as e:
        print(f"Error viewing conversation: {str(e)}")
        flash('Error viewing conversation. Please try again.', 'danger')
        return redirect(url_for('messages'))

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    try:
        listing_id = request.form.get('listing_id')
        recipient_id = request.form.get('recipient_id')
        content = request.form.get('content')
        
        if not all([listing_id, recipient_id, content]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Find conversation
        conversation = messages_collection.find_one({
            'listing_id': listing_id,
            'participants': {'$all': [current_user.id, recipient_id]}
        })
        
        if not conversation:
            return jsonify({'error': 'Conversation not found'}), 404
        
        # Check if this is an offer message
        is_offer = False
        transaction_id = None
        if content.startswith('💰 New offer:'):
            is_offer = True
            # Create a new transaction for the offer
            new_transaction = {
                'listing_id': listing_id,
                'buyer_id': current_user.id,
                'seller_id': recipient_id,
                'price': float(content.split('$')[1].split(' ')[0]),
                'status': 'pending',
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            result = transactions_collection.insert_one(new_transaction)
            transaction_id = str(result.inserted_id)
        
        # Add message
        new_message = {
            'sender_id': current_user.id,
            'content': content,
            'sent_at': datetime.utcnow(),
            'read': False,
            'is_offer': is_offer
        }
        
        if transaction_id:
            new_message['transaction_id'] = transaction_id
        
        messages_collection.update_one(
            {'_id': conversation['_id']},
            {
                '$push': {'messages': new_message},
                '$set': {'last_message': datetime.utcnow()}
            }
        )
        
        # Send email notification if recipient has email notifications enabled
        recipient = users_collection.find_one({'_id': ObjectId(recipient_id)})
        if recipient and recipient.get('settings', {}).get('email_notifications', True):
            try:
                listing = listings_collection.find_one({'_id': ObjectId(listing_id)})
                msg = Message(
                    subject=f'New message about "{listing["title"]}"',
                    sender=app.config['MAIL_DEFAULT_SENDER'],
                    recipients=[recipient['email']],
                    html=render_template('message_notification.html',
                                       sender=current_user,
                                       listing=listing,
                                       message=new_message,
                                       conversation_id=str(conversation['_id']))
                )
                mail.send(msg)
            except Exception as e:
                print(f"Error sending email notification: {str(e)}")
        
        return jsonify({
            'status': 'success',
            'message': {
                'content': content,
                'sent_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                'is_offer': is_offer,
                'transaction_id': transaction_id
            }
        })
    except Exception as e:
        print(f"Error sending message: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/transactions')
@login_required
def transactions():

    user_transactions = list(transactions_collection.find({
        '$or': [
            {'buyer_id': current_user.id},
            {'seller_id': current_user.id}
        ]
    }).sort('created_at', -1))
    
    return render_template('transactions.html', transactions=user_transactions)

@app.route('/howitworks')
def how_it_works():
    return render_template('howitworks.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        
        try:
            # Create email message
            msg = Message(
                subject=f'New Contact Form Submission from {name}',
                sender=email,
                recipients=['vaishnavanand90@gmail.com'],
                body=f'''New message from the contact form:
                
Name: {name}
Email: {email}

Message:
{message}
'''
            )
            mail.send(msg)
            flash('Thank you for your message! We will get back to you soon.', 'success')
        except Exception as e:
            print(f"Error sending email: {str(e)}")
            flash('Sorry, there was an error sending your message. Please try again later.', 'danger')
        
        return redirect(url_for('contact'))
    
    return render_template('contact.html')

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

@app.route('/save_listing/<listing_id>', methods=['POST'])
@login_required
def save_listing(listing_id):
    try:

        existing = saved_items_collection.find_one({
            'user_id': current_user.id,
            'listing_id': listing_id
        })
        
        if existing:

            saved_items_collection.delete_one({'_id': existing['_id']})
            listings_collection.update_one(
                {'_id': ObjectId(listing_id)},
                {'$inc': {'saves': -1}}
            )
            status = 'unsaved'
        else:

            saved_items_collection.insert_one({
                'user_id': current_user.id,
                'listing_id': listing_id,
                'saved_at': datetime.utcnow()
            })
            listings_collection.update_one(
                {'_id': ObjectId(listing_id)},
                {'$inc': {'saves': 1}}
            )
            status = 'saved'

        listing = listings_collection.find_one({'_id': ObjectId(listing_id)})
        saves_count = listing.get('saves', 0) if listing else 0
        
        return jsonify({'status': status, 'saves': saves_count})
    except:
        return jsonify({'error': 'Failed to save listing'}), 400

@app.route('/handle_offer/<transaction_id>', methods=['POST'])
@login_required
def handle_offer(transaction_id):
    try:
        action = request.form.get('action')
        if not action:
            return jsonify({'error': 'Action is required'}), 400
            
        # Get the transaction
        transaction = transactions_collection.find_one({'_id': ObjectId(transaction_id)})
        if not transaction:
            return jsonify({'error': 'Transaction not found'}), 404
            
        # Verify user is the seller
        if transaction['seller_id'] != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403
            
        # Get the listing
        listing = listings_collection.find_one({'_id': ObjectId(transaction['listing_id'])})
        if not listing:
            return jsonify({'error': 'Listing not found'}), 404
            
        # Get the conversation
        conversation = messages_collection.find_one({
            'listing_id': transaction['listing_id'],
            'participants': {'$all': [transaction['buyer_id'], transaction['seller_id']]}
        })
        if not conversation:
            return jsonify({'error': 'Conversation not found'}), 404
            
        if action == 'accept':
            # Update transaction status
            transactions_collection.update_one(
                {'_id': ObjectId(transaction_id)},
                {'$set': {
                    'status': 'accepted',
                    'updated_at': datetime.utcnow()
                }}
            )
            
            # Update listing status
            listings_collection.update_one(
                {'_id': ObjectId(transaction['listing_id'])},
                {'$set': {
                    'status': 'sold',
                    'sold_to': transaction['buyer_id'],
                    'sold_at': datetime.utcnow()
                }}
            )
            
            # Add acceptance message to conversation
            messages_collection.update_one(
                {'_id': conversation['_id']},
                {
                    '$push': {
                        'messages': {
                            'sender_id': current_user.id,
                            'content': '✅ Offer accepted! The item has been marked as sold.',
                            'sent_at': datetime.utcnow(),
                            'read': False,
                            'is_system': True
                        }
                    },
                    '$set': {'last_message': datetime.utcnow()}
                }
            )
            
        elif action == 'decline':
            # Update transaction status
            transactions_collection.update_one(
                {'_id': ObjectId(transaction_id)},
                {'$set': {
                    'status': 'declined',
                    'updated_at': datetime.utcnow()
                }}
            )
            
            # Add decline message to conversation
            messages_collection.update_one(
                {'_id': conversation['_id']},
                {
                    '$push': {
                        'messages': {
                            'sender_id': current_user.id,
                            'content': '❌ Offer declined.',
                            'sent_at': datetime.utcnow(),
                            'read': False,
                            'is_system': True
                        }
                    },
                    '$set': {'last_message': datetime.utcnow()}
                }
            )
            
        elif action == 'counter':
            counter_price = request.form.get('counter_price')
            if not counter_price:
                return jsonify({'error': 'Counter price is required'}), 400
                
            try:
                counter_price = float(counter_price)
            except ValueError:
                return jsonify({'error': 'Invalid counter price'}), 400
                
            # Create new transaction for counter offer
            new_transaction = {
                'listing_id': transaction['listing_id'],
                'buyer_id': transaction['seller_id'],  # Original seller is now making an offer
                'seller_id': transaction['buyer_id'],  # Original buyer is now receiving the offer
                'price': counter_price,
                'status': 'pending',
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            result = transactions_collection.insert_one(new_transaction)
            
            # Add counter offer message to conversation
            messages_collection.update_one(
                {'_id': conversation['_id']},
                {
                    '$push': {
                        'messages': {
                            'sender_id': current_user.id,
                            'content': f'💰 New counter offer: ${counter_price:.2f}',
                            'sent_at': datetime.utcnow(),
                            'read': False,
                            'is_offer': True,
                            'transaction_id': str(result.inserted_id)
                        }
                    },
                    '$set': {'last_message': datetime.utcnow()}
                }
            )
            
        # Send notification to the buyer
        buyer = users_collection.find_one({'_id': ObjectId(transaction['buyer_id'])})
        if buyer and buyer.get('settings', {}).get('email_notifications', True):
            try:
                msg = Message(
                    subject=f'Update on your offer for "{listing["title"]}"',
                    sender=app.config['MAIL_DEFAULT_SENDER'],
                    recipients=[buyer['email']],
                    html=render_template('offer_update_notification.html',
                                       action=action,
                                       listing=listing,
                                       price=transaction['price'],
                                       counter_price=counter_price if action == 'counter' else None)
                )
                mail.send(msg)
            except Exception as e:
                print(f"Error sending email notification: {str(e)}")
        
        return jsonify({'status': 'success'})
        
    except Exception as e:
        print(f"Error handling offer: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/complete_transaction/<transaction_id>', methods=['POST'])
@login_required
def complete_transaction(transaction_id):
    try:
        transaction = transactions_collection.find_one({
            '_id': ObjectId(transaction_id),
            'status': 'accepted'
        })
        
        if not transaction:
            flash('Transaction not found or not in accepted status.', 'danger')
            return redirect(url_for('messages'))
        
        if transaction['seller_id'] != current_user.id:
            flash('Only the seller can complete the transaction.', 'danger')
            return redirect(url_for('messages'))
        
        final_price = transaction.get('final_price', transaction.get('counter_price', transaction['price']))
        transactions_collection.update_one(
            {'_id': ObjectId(transaction_id)},
            {
                '$set': {
                    'status': 'completed',
                    'completed_at': datetime.utcnow(),
                    'final_price': final_price,
                    'updated_at': datetime.utcnow()
                }
            }
        )
        
        listings_collection.update_one(
            {'_id': ObjectId(transaction['listing_id'])},
            {'$set': {'status': 'sold'}}
        )
        
        users_collection.update_one(
            {'_id': ObjectId(transaction['seller_id'])},
            {'$inc': {'stats.sold_count': 1}}
        )
        
        conversation = messages_collection.find_one({
            'listing_id': transaction['listing_id'],
            'participants': {'$all': [transaction['buyer_id'], transaction['seller_id']]}
        })
        
        if conversation:
            completion_message = {
                'sender_id': current_user.id,
                'content': f"🎉 Transaction completed! Final price: ${final_price:.2f}. Thank you for your business!",
                'sent_at': datetime.utcnow(),
                'read': False,
                'is_system': True
            }
            messages_collection.update_one(
                {'_id': conversation['_id']},
                {
                    '$push': {'messages': completion_message},
                    '$set': {'last_message': datetime.utcnow()}
                }
            )
        
        flash('Transaction marked as completed! 🎉', 'success')
        return redirect(url_for('messages'))
        
    except Exception as e:
        print(f"Error completing transaction: {str(e)}")
        flash('Error completing transaction. Please try again.', 'danger')
        return redirect(url_for('messages'))

@app.route('/my_listings')
@login_required
def my_listings():
    # Convert current_user.id to string for MongoDB query
    listings = list(listings_collection.find({'seller_id': str(current_user.id)}).sort('created_at', -1))
    
    offers_by_listing = {}
    for listing in listings:
        listing_id = str(listing['_id'])
        
        # Get all offers for this listing
        offers = list(transactions_collection.find({
            'listing_id': listing_id,
            'seller_id': str(current_user.id)
        }).sort('created_at', -1))
        
        # Enhance offers with buyer information
        enhanced_offers = []
        for offer in offers:
            buyer = users_collection.find_one({'_id': ObjectId(offer['buyer_id'])})
            offer['buyer_info'] = buyer
            enhanced_offers.append(offer)
        
        offers_by_listing[listing_id] = enhanced_offers
    
    return render_template('my_listings.html', 
                         listings=listings,
                         offers_by_listing=offers_by_listing)

@app.route('/edit_listing/<listing_id>', methods=['GET', 'POST'])
@login_required
def edit_listing(listing_id):
    listing = listings_collection.find_one({'_id': ObjectId(listing_id)})
    
    if not listing or listing['seller_id'] != current_user.id:
        flash('Listing not found or you are not the owner', 'danger')
        return redirect(url_for('my_listings'))
    
    if request.method == 'POST':

        updates = {
            'title': request.form['title'],
            'description': request.form['description'],
            'price': float(request.form['price']),
            'category': request.form['category'],
            'size': request.form['size'],
            'condition': request.form['condition'],
            'neighborhood': request.form['neighborhood'],
            'updated_at': datetime.utcnow()
        }
        

        if 'images' in request.files:
            files = request.files.getlist('images')
            new_images = []
            for file in files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                    filename = timestamp + filename
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    new_images.append(filename)
            
            if new_images:
                updates['images'] = new_images
        
        listings_collection.update_one(
            {'_id': ObjectId(listing_id)},
            {'$set': updates}
        )
        
        flash('Listing updated successfully!', 'success')
        return redirect(url_for('listing_detail', listing_id=listing_id))
    

    categories = list(categories_collection.find())
    neighborhoods = list(neighborhoods_collection.find())
    
    return render_template('edit_listing.html', 
                         listing=listing,
                         categories=categories,
                         neighborhoods=neighborhoods)

@app.route('/delete_listing/<listing_id>', methods=['POST'])
@login_required
def delete_listing(listing_id):
    listing = listings_collection.find_one({'_id': ObjectId(listing_id)})
    

    if not listing or listing['seller_id'] != current_user.id:
        flash('Listing not found or you are not the owner', 'danger')
        return redirect(url_for('my_listings'))
    
    listings_collection.delete_one({'_id': ObjectId(listing_id)})
    
    saved_items_collection.delete_many({'listing_id': listing_id})
    
    flash('Listing deleted successfully', 'success')
    return redirect(url_for('home'))

@app.route('/create_transaction', methods=['POST'])
@login_required
def create_transaction():
    try:

        listing_id = request.form['listing_id']
        seller_id = request.form['seller_id']
        price = float(request.form['price'])
        

        if seller_id == current_user.id:
            flash("You cannot make an offer on your own listing", 'danger')
            return redirect(url_for('listing_detail', listing_id=listing_id))
        
        existing_offer = transactions_collection.find_one({
            'listing_id': listing_id,
            'buyer_id': current_user.id,
            'status': {'$in': ['pending', 'countered']}
        })
        
        if existing_offer:
            flash("You already have a pending offer for this item", 'warning')
            return redirect(url_for('listing_detail', listing_id=listing_id))
        
        listing = listings_collection.find_one({'_id': ObjectId(listing_id)})
        if not listing or listing['status'] != 'available':
            flash("This item is no longer available", 'danger')
            return redirect(url_for('home'))
        
        new_transaction = {
            'listing_id': listing_id,
            'buyer_id': current_user.id,
            'seller_id': seller_id,
            'price': price,
            'status': 'pending',
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        result = transactions_collection.insert_one(new_transaction)
        transaction_id = str(result.inserted_id)
        
        conversation = messages_collection.find_one({
            'listing_id': listing_id,
            'participants': {'$all': [current_user.id, seller_id]}
        })
        
        buyer = users_collection.find_one({'_id': ObjectId(current_user.id)})
        
        new_message = {
            'sender_id': current_user.id,
            'content': f"💰 New offer: ${price:.2f} for '{listing['title']}'",
            'sent_at': datetime.utcnow(),
            'read': False,
            'is_offer': True,
            'transaction_id': transaction_id
        }
        
        if conversation:

            messages_collection.update_one(
                {'_id': conversation['_id']},
                {
                    '$push': {'messages': new_message},
                    '$set': {'last_message': datetime.utcnow()}
                }
            )
        else:
  
            new_conversation = {
                'listing_id': listing_id,
                'participants': [current_user.id, seller_id],
                'messages': [new_message],
                'created_at': datetime.utcnow(),
                'last_message': datetime.utcnow()
            }
            messages_collection.insert_one(new_conversation)
        
        flash(f'Your offer of ${price:.2f} has been submitted!', 'success')
        return redirect(url_for('messages'))
        
    except Exception as e:
        print(f"Error creating transaction: {str(e)}")
        flash('Error creating offer. Please try again.', 'danger')
        return redirect(url_for('listing_detail', listing_id=listing_id))

@app.route('/update_listing/<listing_id>', methods=['POST'])
@login_required
def update_listing(listing_id):
    """Handle quick status updates for listings"""
    listing = listings_collection.find_one({'_id': ObjectId(listing_id)})
    
    if not listing or listing['seller_id'] != current_user.id:
        flash('Listing not found or you are not the owner', 'danger')
        return redirect(url_for('my_listings'))
    
    if 'status' in request.form:
        new_status = request.form['status']
        if new_status in ['available', 'sold', 'pending']:
            listings_collection.update_one(
                {'_id': ObjectId(listing_id)},
                {'$set': {'status': new_status, 'updated_at': datetime.utcnow()}}
            )
            flash(f'Listing status updated to {new_status}', 'success')
        else:
            flash('Invalid status', 'danger')
    
    return redirect(url_for('my_listings'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        # Get form data
        username = request.form.get('username')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        school = request.form.get('school')
        
        # Initialize updates dictionary
        updates = {}
        
        # Check if username is being changed
        if username and username != current_user.username:
            # Check if new username is available
            if users_collection.find_one({'username': username, '_id': {'$ne': ObjectId(current_user.id)}}):
                flash('Username already taken. Please choose another.', 'danger')
            else:
                updates['username'] = username
        
        # Check if password is being changed
        if current_password and new_password:
            # Verify current password
            user_data = users_collection.find_one({'_id': ObjectId(current_user.id)})
            if bcrypt.check_password_hash(user_data['password'], current_password):
                updates['password'] = bcrypt.generate_password_hash(new_password).decode('utf-8')
            else:
                flash('Current password is incorrect.', 'danger')
        
        # Check if school is being changed
        if school and school != current_user.user_data.get('profile', {}).get('school', ''):
            updates['profile.school'] = school
        
        # Apply updates if any
        if updates:
            updates['updated_at'] = datetime.utcnow()
            users_collection.update_one(
                {'_id': ObjectId(current_user.id)},
                {'$set': updates}
            )
            
            # Refresh user data
            user_data = users_collection.find_one({'_id': ObjectId(current_user.id)})
            login_user(User(user_data))
            
            flash('Profile updated successfully!', 'success')
        
        return redirect(url_for('profile'))
    
    # Get user's listings with their offers
    my_listings = list(listings_collection.find({'seller_id': str(current_user.id)}).sort('created_at', -1))
    
    # Enhance listings with offers
    for listing in my_listings:
        # Get all offers for this listing
        offers = list(transactions_collection.find({
            'listing_id': str(listing['_id']),
            'seller_id': str(current_user.id)
        }).sort('created_at', -1))
        
        # Enhance offers with buyer information
        enhanced_offers = []
        for offer in offers:
            buyer = users_collection.find_one({'_id': ObjectId(offer['buyer_id'])})
            if buyer:
                offer['buyer_username'] = buyer['username']
            enhanced_offers.append(offer)
        
        listing['offers'] = enhanced_offers
    
    # Get user's inquiries (offers made on other listings)
    my_inquiries = list(transactions_collection.find({
        'buyer_id': str(current_user.id)
    }).sort('created_at', -1))
    
    # Enhance inquiries with listing information
    enhanced_inquiries = []
    for inquiry in my_inquiries:
        listing = listings_collection.find_one({'_id': ObjectId(inquiry['listing_id'])})
        if listing:
            inquiry['listing'] = listing
            enhanced_inquiries.append(inquiry)
    
    # Get user data for display
    user_data = users_collection.find_one({'_id': ObjectId(current_user.id)})
    return render_template('profile.html', 
                         user=user_data, 
                         my_listings=my_listings,
                         my_inquiries=enhanced_inquiries)

def timeago(timestamp):
    """Convert a timestamp to "time ago" text."""
    if not timestamp:
        return ""
        
    # Make sure both timestamps are timezone-aware
    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
    else:
        return ""
    
    now = datetime.now(timezone.utc)
    diff = now - timestamp

    seconds = diff.total_seconds()
    if seconds < 60:
        return 'just now'
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f'{minutes}m ago'
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f'{hours}h ago'
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f'{days}d ago'
    elif seconds < 2592000:
        weeks = int(seconds / 604800)
        return f'{weeks}w ago'
    elif seconds < 31536000:
        months = int(seconds / 2592000)
        return f'{months}mo ago'
    else:
        years = int(seconds / 31536000)
        return f'{years}y ago'

# Register the filter with Jinja2
app.jinja_env.filters['timeago'] = timeago

# Socket.IO event handlers
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room(current_user.id)

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        leave_room(current_user.id)

@socketio.on('join_conversation')
def handle_join_conversation(data):
    if current_user.is_authenticated:
        conversation_id = data.get('conversation_id')
        if conversation_id:
            join_room(conversation_id)

@socketio.on('leave_conversation')
def handle_leave_conversation(data):
    if current_user.is_authenticated:
        conversation_id = data.get('conversation_id')
        if conversation_id:
            leave_room(conversation_id)

@socketio.on('typing')
def handle_typing(data):
    if current_user.is_authenticated:
        conversation_id = data.get('conversation_id')
        if conversation_id:
            emit('typing', {
                'sender_id': current_user.id,
                'conversation_id': conversation_id
            }, room=conversation_id)

@socketio.on('stop_typing')
def handle_stop_typing(data):
    if current_user.is_authenticated:
        conversation_id = data.get('conversation_id')
        if conversation_id:
            emit('stop_typing', {
                'sender_id': current_user.id,
                'conversation_id': conversation_id
            }, room=conversation_id)

@app.route('/start_conversation/<listing_id>', methods=['GET'])
@login_required
def start_conversation(listing_id):
    try:
        # Get listing
        listing = listings_collection.find_one({'_id': ObjectId(listing_id)})
        if not listing:
            flash('Listing not found.', 'danger')
            return redirect(url_for('listings'))
        
        # Can't message your own listing
        if listing['seller_id'] == current_user.id:
            flash('You cannot message yourself about your own listing.', 'warning')
            return redirect(url_for('listing_detail', listing_id=listing_id))
        
        # Find existing conversation or create new one
        conversation = messages_collection.find_one({
            'listing_id': listing_id,
            'participants': {'$all': [current_user.id, listing['seller_id']]}
        })
        
        if not conversation:
            # Create new conversation
            conversation = {
                'listing_id': listing_id,
                'participants': [current_user.id, listing['seller_id']],
                'messages': [],
                'last_message': datetime.utcnow(),
                'created_at': datetime.utcnow()
            }
            result = messages_collection.insert_one(conversation)
            conversation_id = result.inserted_id
        else:
            conversation_id = conversation['_id']
        
        return redirect(url_for('conversation', conversation_id=conversation_id))
    except Exception as e:
        print(f"Error starting conversation: {str(e)}")
        flash('Error starting conversation. Please try again.', 'danger')
        return redirect(url_for('listing_detail', listing_id=listing_id))

@socketio.on('new_message')
def handle_new_message(data):
    if current_user.is_authenticated:
        conversation_id = data.get('conversation_id')
        if conversation_id:
            emit('new_message', data, room=conversation_id)

# Notification routes and functions
@app.route('/api/notifications/<notification_id>/dismiss', methods=['POST'])
@login_required
def dismiss_notification(notification_id):
    try:
        # Mark notification as read
        db.notifications.update_one(
            {'_id': ObjectId(notification_id), 'user_id': current_user.id},
            {'$set': {'read': True}}
        )
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

def create_notification(user_id, type, message, action_url):
    notification = {
        'user_id': user_id,
        'type': type,
        'message': message,
        'action_url': action_url,
        'read': False,
        'created_at': datetime.utcnow()
    }
    db.notifications.insert_one(notification)

@app.route('/api/offers/<offer_id>/accept', methods=['POST'])
@login_required
def accept_offer(offer_id):
    try:
        offer = db.offers.find_one({'_id': ObjectId(offer_id)})
        if not offer:
            return jsonify({'status': 'error', 'message': 'Offer not found'})
            
        # Update offer status
        db.offers.update_one(
            {'_id': ObjectId(offer_id)},
            {'$set': {'status': 'accepted'}}
        )
        
        # Update listing status
        db.listings.update_one(
            {'_id': offer['listing_id']},
            {'$set': {'status': 'sold'}}
        )
        
        # Create notification for buyer
        create_notification(
            offer['buyer_id'],
            'offer_accepted',
            f'Your offer for {offer["listing_title"]} has been accepted!',
            url_for('listing_detail', listing_id=str(offer['listing_id']))
        )
        
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/offers/<offer_id>/decline', methods=['POST'])
@login_required
def decline_offer(offer_id):
    try:
        offer = db.offers.find_one({'_id': ObjectId(offer_id)})
        if not offer:
            return jsonify({'status': 'error', 'message': 'Offer not found'})
            
        # Update offer status
        db.offers.update_one(
            {'_id': ObjectId(offer_id)},
            {'$set': {'status': 'declined'}}
        )
        
        # Create notification for buyer
        create_notification(
            offer['buyer_id'],
            'offer_declined',
            f'Your offer for {offer["listing_title"]} has been declined.',
            url_for('listing_detail', listing_id=str(offer['listing_id']))
        )
        
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/listing_status')
@login_required
def listing_status():
    # Get user's listings
    my_listings = list(db.listings.find({'seller_id': current_user.id}))
    for listing in my_listings:
        # Get offers for each listing
        listing['offers'] = list(db.offers.find({'listing_id': listing['_id']}))
        
    # Get listings user has made offers on
    interested_listings = []
    my_offers = list(db.offers.find({'buyer_id': current_user.id}))
    for offer in my_offers:
        listing = db.listings.find_one({'_id': offer['listing_id']})
        if listing:
            listing['my_offer'] = offer
            interested_listings.append(listing)
            
    return render_template('listing_status.html', 
                         my_listings=my_listings,
                         interested_listings=interested_listings)

@app.context_processor
def inject_notifications():
    if current_user.is_authenticated:
        notifications = list(
            db.notifications.find({
                'user_id': current_user.id,
                'read': False
            }).sort('created_at', -1)
        )
        return {'notifications': notifications}
    return {'notifications': []}

@app.route('/flag_listing/<listing_id>', methods=['POST'])
@login_required
def flag_listing(listing_id):
    try:
        # Check if user has already flagged this listing
        existing_flag = flags_collection.find_one({
            'listing_id': listing_id,
            'user_id': str(current_user.id)
        })
        
        if existing_flag:
            return jsonify({
                'status': 'error',
                'message': 'You have already flagged this listing'
            }), 400
        
        # Add new flag
        new_flag = {
            'listing_id': listing_id,
            'user_id': str(current_user.id),
            'reason': request.form.get('reason', 'inappropriate'),
            'created_at': datetime.utcnow()
        }
        flags_collection.insert_one(new_flag)
        
        # Count total flags for this listing
        flag_count = flags_collection.count_documents({'listing_id': listing_id})
        
        # If 3 or more flags, take down the listing
        if flag_count >= 3:
            # Update listing status
            listing = listings_collection.find_one({'_id': ObjectId(listing_id)})
            listings_collection.update_one(
                {'_id': ObjectId(listing_id)},
                {'$set': {
                    'status': 'flagged',
                    'flagged_at': datetime.utcnow()
                }}
            )
            
            # Notify seller
            if listing:
                create_notification(
                    listing['seller_id'],
                    'listing_flagged',
                    f'Your listing "{listing["title"]}" has been taken down due to multiple user reports.',
                    url_for('listing_detail', listing_id=listing_id)
                )
                
                # Send email to seller
                seller = users_collection.find_one({'_id': ObjectId(listing['seller_id'])})
                if seller and seller.get('email'):
                    try:
                        msg = Message(
                            subject='Your listing has been flagged',
                            sender=app.config['MAIL_DEFAULT_SENDER'],
                            recipients=[seller['email']],
                            html=render_template('email/listing_flagged.html',
                                               listing=listing,
                                               flag_count=flag_count)
                        )
                        mail.send(msg)
                    except Exception as e:
                        print(f"Error sending email: {str(e)}")
        
        return jsonify({
            'status': 'success',
            'message': 'Listing has been flagged',
            'flag_count': flag_count
        })
        
    except Exception as e:
        print(f"Error flagging listing: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'An error occurred while flagging the listing'
        }), 500

@app.route('/listing/<listing_id>/flag_status')
@login_required
def flag_status(listing_id):
    try:
        # Check if user has flagged this listing
        has_flagged = flags_collection.find_one({
            'listing_id': listing_id,
            'user_id': str(current_user.id)
        }) is not None
        
        # Get total flag count
        flag_count = flags_collection.count_documents({'listing_id': listing_id})
        
        return jsonify({
            'has_flagged': has_flagged,
            'flag_count': flag_count
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    socketio.run(app, debug=True)