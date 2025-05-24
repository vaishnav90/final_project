from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
import smtplib

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this to a secure secret key

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

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'  # Replace with your email
app.config['MAIL_PASSWORD'] = 'your-email-password'  # Replace with your email password or app password
app.config['MAIL_DEFAULT_SENDER'] = 'your-email@gmail.com'

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
    # Get recent listings
    recent_listings = list(listings_collection.find({'status': 'available'})
                          .sort('created_at', -1)
                          .limit(8))
    
    # Get high-end listings (price > $100)
    high_end_listings = list(listings_collection.find({
        'status': 'available',
        'price': {'$gt': 100}
    }).sort('created_at', -1).limit(4))
    
    # Get popular categories with item counts
    pipeline = [
        {'$match': {'status': 'available'}},
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
                         recent_listings=recent_listings,
                         high_end_listings=high_end_listings,
                         popular_categories=popular_categories)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
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
                'avatar': '',
                'bio': '',
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
    # Get filter parameters
    neighborhood = request.args.get('neighborhood', 'all')
    category = request.args.get('category', 'all')
    price_min = request.args.get('price_min', type=int)
    price_max = request.args.get('price_max', type=int)
    search = request.args.get('search', '')
    
    # Build query
    query = {'status': 'available'}
    
    if neighborhood != 'all':
        query['neighborhood'] = neighborhood
    
    if category != 'all':
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
    
    # Get listings
    listings = list(listings_collection.find(query).sort('created_at', -1))
    
    # Get filter options
    neighborhoods = list(neighborhoods_collection.find())
    categories = list(categories_collection.find())
    
    return render_template('listings.html', 
                         listings=listings,
                         neighborhoods=neighborhoods,
                         categories=categories,
                         selected_neighborhood=neighborhood,
                         selected_category=category,
                         search_query=search)

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
        images = []
        if 'images' in request.files:
            files = request.files.getlist('images')
            print("Files received:", files)  # Debugging
            for file in files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                    filename = timestamp + filename
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    print("Saving file to:", filepath)  # Debugging
                    file.save(filepath)
                    images.append(filename)
        
        print("Uploaded images:", images)  # Debugging
        
        new_listing = {
            'title': request.form['title'],
            'description': request.form['description'],
            'price': float(request.form['price']),
            'category': request.form['category'],
            'size': request.form['size'],
            'condition': request.form['condition'],
            'neighborhood': request.form['neighborhood'],
            'images': images,
            'status': 'available',
            'seller_id': current_user.id,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'views': 0,
            'saves': 0
        }
        
        listings_collection.insert_one(new_listing)
        flash('Your item has been listed successfully!', 'success')
        return redirect(url_for('home'))
    
    categories = list(categories_collection.find())
    neighborhoods = list(neighborhoods_collection.find())
    return render_template('sell.html', categories=categories, neighborhoods=neighborhoods)

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
        # Get all conversations where current user is a participant
        conversations = list(messages_collection.find({
            'participants': current_user.id
        }).sort('last_message', -1))

        if not conversations:
            return render_template('messages.html', conversations=[])

        # Prepare data for template
        enhanced_conversations = []
        
        for conv in conversations:
            # Get listing info
            listing = listings_collection.find_one({'_id': ObjectId(conv['listing_id'])})
            
            # Get other participant info
            other_user_id = next(p for p in conv['participants'] if p != current_user.id)
            other_user = users_collection.find_one({'_id': ObjectId(other_user_id)})
            
            # Get transaction if exists
            transaction = None
            if 'transaction_id' in conv:
                transaction = transactions_collection.find_one({
                    '_id': ObjectId(conv['transaction_id'])
                })

            enhanced_conversations.append({
                'conversation': conv,
                'listing': listing,
                'other_user': other_user,
                'transaction': transaction  # Include transaction directly
            })

        return render_template('messages.html', 
                            conversations=enhanced_conversations)
    
    except Exception as e:
        print(f"Error loading messages: {str(e)}")
        flash('Error loading messages', 'danger')
        return redirect(url_for('home'))
@app.route('/messages/<conversation_id>')
@login_required
def conversation(conversation_id):
    try:
        conversation = messages_collection.find_one({
            '_id': ObjectId(conversation_id),
            'participants': current_user.id
        })
        
        if not conversation:
            flash('Conversation not found.', 'danger')
            return redirect(url_for('messages'))
        
        # Get listing and other user info
        listing = listings_collection.find_one({'_id': ObjectId(conversation['listing_id'])})
        other_user_id = [p for p in conversation['participants'] if p != current_user.id][0]
        other_user = users_collection.find_one({'_id': ObjectId(other_user_id)})
        
        return render_template('conversation.html', 
                             conversation=conversation,
                             listing=listing,
                             other_user=other_user)
    except:
        flash('Invalid conversation ID.', 'danger')
        return redirect(url_for('messages'))

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    try:
        listing_id = request.form['listing_id']
        recipient_id = request.form['recipient_id']
        content = request.form['content']
        
        # Find existing conversation//
        conversation = messages_collection.find_one({
            'listing_id': listing_id,
            'participants': {'$all': [current_user.id, recipient_id]}
        })
        
        new_message = {
            'sender_id': current_user.id,
            'content': content,
            'sent_at': datetime.utcnow(),
            'read': False
        }
        
        if conversation:
            # Add message to existing conversation
            messages_collection.update_one(
                {'_id': conversation['_id']},
                {
                    '$push': {'messages': new_message},
                    '$set': {'last_message': datetime.utcnow()}
                }
            )
            conversation_id = str(conversation['_id'])
        else:
            # Create new conversation
            new_conversation = {
                'listing_id': listing_id,
                'participants': [current_user.id, recipient_id],
                'messages': [new_message],
                'last_message': datetime.utcnow(),
                'created_at': datetime.utcnow()
            }
            result = messages_collection.insert_one(new_conversation)
            conversation_id = str(result.inserted_id)
        
        return jsonify({
            'status': 'success',
            'conversation_id': conversation_id,
            'message': {
                'content': content,
                'sent_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M')
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/transactions')
@login_required
def transactions():
    # Get user's transactions
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

# Error handlers
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
        # Check if already saved
        existing = saved_items_collection.find_one({
            'user_id': current_user.id,
            'listing_id': listing_id
        })
        
        if existing:
            # Remove from saved items
            saved_items_collection.delete_one({'_id': existing['_id']})
            listings_collection.update_one(
                {'_id': ObjectId(listing_id)},
                {'$inc': {'saves': -1}}
            )
            status = 'unsaved'
        else:
            # Add to saved items
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
        
        # Get updated saves count
        listing = listings_collection.find_one({'_id': ObjectId(listing_id)})
        saves_count = listing.get('saves', 0) if listing else 0
        
        return jsonify({'status': status, 'saves': saves_count})
    except:
        return jsonify({'error': 'Failed to save listing'}), 400

@app.route('/handle_offer/<transaction_id>', methods=['POST'])
@login_required
def handle_offer(transaction_id):
    try:
        action = request.form['action']
        transaction = transactions_collection.find_one({'_id': ObjectId(transaction_id)})
        
        if not transaction:
            flash('Transaction not found.', 'danger')
            return redirect(url_for('transactions'))
        
        if transaction['seller_id'] != current_user.id:
            flash('You are not authorized to handle this offer.', 'danger')
            return redirect(url_for('transactions'))
        
        listing = listings_collection.find_one({'_id': ObjectId(transaction['listing_id'])})
        
        if action == 'accept':
            # Accept the offer
            transactions_collection.update_one(
                {'_id': ObjectId(transaction_id)},
                {'$set': {
                    'status': 'accepted',
                    'updated_at': datetime.utcnow()
                }}
            )
            
            # Mark listing as sold
            listings_collection.update_one(
                {'_id': ObjectId(transaction['listing_id'])},
                {'$set': {'status': 'sold'}}
            )
            
            # Send message to buyer
            messages_collection.update_one(
                {'transaction_id': transaction_id},
                {'$push': {
                    'messages': {
                        'sender_id': current_user.id,
                        'content': f"I've accepted your offer of ${transaction['price']}! Let's arrange the pickup.",
                        'sent_at': datetime.utcnow(),
                        'read': False
                    }
                }}
            )
            
            flash('Offer accepted! The item has been marked as sold.', 'success')
            
        elif action == 'decline':
            # Decline the offer
            transactions_collection.update_one(
                {'_id': ObjectId(transaction_id)},
                {'$set': {
                    'status': 'declined',
                    'updated_at': datetime.utcnow()
                }}
            )
            
            # Reopen listing if it was pending
            if listing['status'] == 'pending':
                listings_collection.update_one(
                    {'_id': ObjectId(transaction['listing_id'])},
                    {'$set': {'status': 'available'}}
                )
            
            # Send message to buyer
            messages_collection.update_one(
                {'transaction_id': transaction_id},
                {'$push': {
                    'messages': {
                        'sender_id': current_user.id,
                        'content': "Thank you for your offer, but I've decided to decline it.",
                        'sent_at': datetime.utcnow(),
                        'read': False
                    }
                }}
            )
            
            flash('Offer declined.', 'info')
            
        elif action == 'counter':
            # Counter the offer
            counter_price = float(request.form['counter_price'])
            
            transactions_collection.update_one(
                {'_id': ObjectId(transaction_id)},
                {'$set': {
                    'status': 'countered',
                    'counter_price': counter_price,
                    'updated_at': datetime.utcnow()
                }}
            )
            
            # Send message to buyer
            messages_collection.update_one(
                {'transaction_id': transaction_id},
                {'$push': {
                    'messages': {
                        'sender_id': current_user.id,
                        'content': f"I've countered your offer with ${counter_price}. What do you think?",
                        'sent_at': datetime.utcnow(),
                        'read': False
                    }
                }}
            )
            
            flash('Counter offer sent!', 'success')
            
        return redirect(url_for('messages'))
    except Exception as e:
        flash(f'Error handling offer: {str(e)}', 'danger')
        return redirect(url_for('transactions'))

@app.route('/complete_transaction/<transaction_id>', methods=['POST'])
@login_required
def complete_transaction(transaction_id):
    try:
        transaction = transactions_collection.find_one({
            '_id': ObjectId(transaction_id),
            '$or': [
                {'buyer_id': current_user.id},
                {'seller_id': current_user.id}
            ]
        })
        
        if not transaction:
            flash('Transaction not found.', 'danger')
            return redirect(url_for('transactions'))
        
        # Only seller can mark as completed
        if transaction['seller_id'] != current_user.id:
            flash('Only the seller can complete the transaction.', 'danger')
            return redirect(url_for('transactions'))
        
        # Update transaction
        transactions_collection.update_one(
            {'_id': ObjectId(transaction_id)},
            {
                '$set': {
                    'status': 'completed',
                    'meeting.completed_at': datetime.utcnow(),
                    'payment.processed': True,
                    'updated_at': datetime.utcnow()
                }
            }
        )
        
        # Update listing status if not already sold
        listings_collection.update_one(
            {'_id': ObjectId(transaction['listing_id'])},
            {'$set': {'status': 'sold'}}
        )
        
        # Update seller's sold count
        users_collection.update_one(
            {'_id': ObjectId(transaction['seller_id'])},
            {'$inc': {'stats.sold_count': 1}}
        )
        
        # Send message to buyer
        messages_collection.update_one(
            {'transaction_id': transaction_id},
            {'$push': {
                'messages': {
                    'sender_id': current_user.id,
                    'content': "The transaction has been marked as completed. Thank you!",
                    'sent_at': datetime.utcnow(),
                    'read': False
                }
            }}
        )
        
        flash('Transaction marked as completed!', 'success')
        return redirect(url_for('transactions'))
    except Exception as e:
        flash(f'Error completing transaction: {str(e)}', 'danger')
        return redirect(url_for('transactions'))
@app.route('/my_listings')
@login_required
def my_listings():
    # Get user's listings
    listings = list(listings_collection.find({'seller_id': current_user.id}).sort('created_at', -1))
    
    return render_template('my_listings.html', listings=listings)

@app.route('/edit_listing/<listing_id>', methods=['GET', 'POST'])
@login_required
def edit_listing(listing_id):
    listing = listings_collection.find_one({'_id': ObjectId(listing_id)})
    
    # Verify listing exists and belongs to current user
    if not listing or listing['seller_id'] != current_user.id:
        flash('Listing not found or you are not the owner', 'danger')
        return redirect(url_for('my_listings'))
    
    if request.method == 'POST':
        # Handle form submission
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
        
        # Handle image updates if needed
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
    
    # For GET request, show edit form
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
    
    # Verify listing exists and belongs to current user
    if not listing or listing['seller_id'] != current_user.id:
        flash('Listing not found or you are not the owner', 'danger')
        return redirect(url_for('my_listings'))
    
    # Delete listing
    listings_collection.delete_one({'_id': ObjectId(listing_id)})
    
    # Also delete any saved items for this listing
    saved_items_collection.delete_many({'listing_id': listing_id})
    
    flash('Listing deleted successfully', 'success')
    return redirect(url_for('my_listings'))
@app.route('/create_transaction', methods=['POST'])
@login_required
def create_transaction():
    try:
        # Get form data
        listing_id = request.form['listing_id']
        seller_id = request.form['seller_id']
        price = float(request.form['price'])
        meeting_method = request.form['meeting_method']
        meeting_location = request.form['meeting_location']
        meeting_time = request.form['meeting_time']
        
        # Get listing and user info
        listing = listings_collection.find_one({'_id': ObjectId(listing_id)})
        seller = users_collection.find_one({'_id': ObjectId(seller_id)})
        buyer = users_collection.find_one({'_id': ObjectId(current_user.id)})
        
        # Create transaction record
        new_transaction = {
            'listing_id': listing_id,
            'buyer_id': current_user.id,
            'seller_id': seller_id,
            'price': price,
            'original_price': listing['price'],
            'status': 'pending',
            'meeting': {
                'method': meeting_method,
                'location': meeting_location,
                'scheduled_time': meeting_time,
                'completed_at': None
            },
            'created_at': datetime.utcnow()
        }
        
        # Save transaction
        transaction_id = str(transactions_collection.insert_one(new_transaction).inserted_id)
        
        # Create or update conversation
        conversation = messages_collection.find_one({
            'listing_id': listing_id,
            'participants': {'$all': [current_user.id, seller_id]}
        })
        
        new_message = {
            'sender_id': current_user.id,
            'content': f"New offer of ${price} for {listing['title']}",
            'sent_at': datetime.utcnow(),
            'read': False,
            'is_offer': True,
            'transaction_id': transaction_id
        }
        
        if conversation:
            # Update existing conversation
            messages_collection.update_one(
                {'_id': conversation['_id']},
                {
                    '$push': {'messages': new_message},
                    '$set': {'last_message': datetime.utcnow()}
                }
            )
            conversation_id = str(conversation['_id'])
        else:
            # Create new conversation
            new_conversation = {
                'listing_id': listing_id,
                'participants': [current_user.id, seller_id],
                'messages': [new_message],
                'created_at': datetime.utcnow(),
                'last_message': datetime.utcnow()
            }
            conversation_id = str(messages_collection.insert_one(new_conversation).inserted_id)
        
        # Update listing status
        listings_collection.update_one(
            {'_id': ObjectId(listing_id)},
            {'$set': {'status': 'pending'}}
        )
        
        flash('Your offer has been submitted!', 'success')
        return redirect(url_for('messages'))
        
    except Exception as e:
        print(f"Error creating transaction: {str(e)}")
        flash('Error creating offer', 'danger')
        return redirect(url_for('listing_detail', listing_id=listing_id))
if __name__ == "__main__":
    app.run(debug=True, port=5002)