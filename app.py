from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import boto3
from datetime import datetime, timedelta
import json, uuid
import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


app=Flask(__name__)
app.secret_key = os.urandom(24)

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
users_table = dynamodb.Table('Users')
orders_table = dynamodb.Table('Orders')


SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))

SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')

ENABLE_EMAIL = os.environ.get('ENABLE_EMAIL', 'False').lower() == 'true'

#SNS Configuration

SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')
ENABLE_SNS = os.environ.get('ENABLE_SNS', 'False').lower() == 'true'

# Initialize SNS client
sns = boto3.client('sns', region_name='us-east-1')

logging.basicConfig(
 level=logging.INFO,
 format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
 handlers=[
 logging.FileHandler("fleetsync.log"),
 logging.StreamHandler()
 ]
)
logger = logging.getLogger(__name__)


#Helper Functions
def is_logged_in():
 return 'email' in session

def get_user_role(email):
 try:
     response = users_table.get_item(Key={'email': email})
     return response.get('Item', {}).get('role')
 except Exception as e:
     logger.error(f"Error fetching role: {e}")
     return None

def send_email(to_email, subject, body):
    if not ENABLE_EMAIL:
        logger.info(f"[Email Skipped] Subject: {subject} to {to_email}")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()

        logger.info(f"Email sent to {to_email}")
    except Exception as e:
        logger.error(f"Email sending failed: {e}")



def publish_to_sns(message, subject="FleetSync Notification"):
    if not ENABLE_SNS:
        logger.info("[SNS Skipped] Message: {}".format(message))
        return

    try:
        response = sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=message,
            Subject=subject
        )
        logger.info(f"SNS published: {response['MessageId']}")
    except Exception as e:
        logger.error(f"SNS publish failed: {e}")

def require_role(required_role):
    def decorator(f):
        def decorated_function(*args, **kwargs):
            if not is_logged_in():
                flash('Please log in to access this page', 'warning')
                return redirect(url_for('login'))
            
            user_role = session.get('role')
            if user_role != required_role and required_role != 'any':
                flash('Access denied. Insufficient permissions.', 'danger')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        decorated_function.__name__ = f.__name__
        return decorated_function
    return decorator

products = {
    'non_vegpickles': [
        {'id': 1, 'image': 'chicken_pickle.jpg', 'name': 'Chicken Pickle', 'weights': {'250': 600, '500': 1200, '1000': 1800}},
        {'id': 2, 'image': 'fish_pickle.jpg', 'name': 'Fish Pickle', 'weights': {'250': 200, '500': 400, '1000': 800}},
        {'id': 3, 'image': 'gongura_mutton.jpg', 'name': 'Gongura Mutton', 'weights': {'250': 400, '500': 800, '1000': 1600}},
        {'id': 4, 'image': 'mutton_pickle.jpg', 'name': 'Mutton Pickle', 'weights': {'250': 400, '500': 800, '1000': 1600}},
        {'id': 5, 'image': 'gongura_prawns.jpg', 'name': 'Gongura Prawns', 'weights': {'250': 600, '500': 1200, '1000': 1800}},
        {'id': 6, 'image': 'chicken_pickle_gongura.jpg', 'name': 'Chicken Pickle (Gongura)', 'weights': {'250': 350, '500': 700, '1000': 1050}}
    ],
    'veg_pickles': [
        {'id': 7, 'image': 'traditional_mango_pickle.jpg', 'name': 'Traditional Mango Pickle', 'weights': {'250': 150, '500': 280, '1000': 500}},
        {'id': 8, 'image': 'zesty_lemon_pickle.jpg', 'name': 'Zesty Lemon Pickle', 'weights': {'250': 120, '500': 220, '1000': 400}},
        {'id': 9, 'image': 'tomato_pickle.jpg', 'name': 'Tomato Pickle', 'weights': {'250': 130, '500': 240, '1000': 450}},
        {'id': 10, 'image': 'kakarakaya_pickle.jpg', 'name': 'Kakarakaya Pickle', 'weights': {'250': 130, '500': 240, '1000': 450}},
        {'id': 11, 'image': 'chintakaya_pickle.png', 'name': 'Chintakaya Pickle', 'weights': {'250': 130, '500': 240, '1000': 450}},
        {'id': 12, 'image': 'spicy_pandu_mirchi.jpg', 'name': 'Spicy Pandu Mirchi', 'weights': {'250': 130, '500': 240, '1000': 450}}
    ], # Add your veg pickle products here
    'snacks': [
        {'id': 13, 'image': 'banana_chips.jpg', 'name': 'Banana Chips', 'weights': {'250': 300, '500': 600, '1000': 800}},
        {'id': 14, 'image': 'crispy_aam_papad.png', 'name': 'Crispy Aam-Papad', 'weights': {'250': 150, '500': 300, '1000': 600}},
        {'id': 16, 'image': 'boondhi_acchu.png', 'name': 'Boondhi Acchu', 'weights': {'250': 300, '500': 600, '1000': 900}},
        {'id': 17, 'image': 'chekkalu.jpg', 'name': 'Chekkalu', 'weights': {'250': 350, '500': 700, '1000': 1000}},
        {'id': 18, 'image': 'ragi_laddu.jpg', 'name': 'Ragi Laddu', 'weights': {'250': 350, '500': 700, '1000': 1000}},
        {'id': 19, 'image': 'dry_fruit_laddu.jpg', 'name': 'Dry Fruit Laddu', 'weights': {'250': 500, '500': 1000, '1000': 1500}},
        {'id': 20, 'image': 'kara_boondi.jpg', 'name': 'Kara Boondi', 'weights': {'250': 250, '500': 500, '1000': 750}},
        {'id': 21, 'image': 'gavvalu.jpg', 'name': 'Gavvalu', 'weights': {'250': 250, '500': 500, '1000': 750}},
        {'id': 22, 'image': 'kaju_chikki.jpg', 'name': 'Kaju Chikki', 'weights': {'250': 250, '500': 500, '1000': 750}}
    ]
}
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            return render_template('login.html', error="Both fields are required.")

        try:
            response = users_table.get_item(Key={'email': email})
            if 'Item' not in response:
                return render_template('login.html', error="User not found")

            user = response['Item']
            if check_password_hash(user['password'], password):
                session['logged_in'] = True
                session['username'] = user.get('username')
                session['email'] = email
                session.setdefault('home', [])
                return redirect(url_for('home'))
            else:
                return render_template('login.html', error="Incorrect password")
        except Exception as e:
            return render_template('login.html', error=f"An error occurred: {str(e)}")

    return render_template('login.html')
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not username or not email or not password:
            return render_template('signup.html', error='All fields are required.')

        try:
            # Check if email (partition key) already exists
            response = users_table.get_item(Key={'email': email})
            if 'Item' in response:
                return render_template('signup.html', error='An account with this email already exists.')

            hashed_password = generate_password_hash(password)

            users_table.put_item(
                Item={
                    'email': email,                # Partition key
                    'username': username,
                    'password': hashed_password,
                }
            )

            return redirect(url_for('login'))

        except Exception as e:
            app.logger.error(f"Signup error: {str(e)}")
            return render_template('signup.html', error='Registration failed. Please try again.')

    return render_template('signup.html')


@app.route('/logout')
def logout():
        session.clear()
        return redirect(url_for('login'))

@app.route('/home')
def home():
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return render_template('home.html')

@app.route('/non_vegpickles')
def non_vegpickles():
    return render_template('non_vegpickles.html', products=products ['non_vegpickles'])

@app.route('/veg_pickles')
def veg_pickles():
    # Simply pass all products without filtering
    return render_template('veg_pickles.html', products=products ['veg_pickles'])                                                               

@app.route('/snacks')
def snacks():
    return render_template('snacks.html', products=products['snacks'])
                
@app.route('/check_out', methods=['GET', 'POST'])
def check_out():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            address = request.form.get('address', '').strip()
            phone = request.form.get('phone', '').strip()
            payment_method = request.form.get('payment', '').strip()

            if not all([name, address, phone, payment_method]):
                return render_template('check_out.html', error="All fields are required.")

            if not phone.isdigit() or len(phone) != 10:
                return render_template('check_out.html', error="Phone number must be exactly 10 digits.")

            cart_data = request.form.get('cart_data', '[]')
            total_amount = request.form.get('total_amount', '0')

            try:
                cart_items = json.loads(cart_data)
                total_amount = float(total_amount)
            except (json.JSONDecodeError, ValueError):
                return render_template('check_out.html', error="Invalid cart data format.")

            if not cart_items:
                return render_template('check_out.html', error="Your cart is empty.")

            # Save to DynamoDB
            orders_table.put_item(
                Item={
                    'order_id': str(uuid.uuid4()),
                    'username': session.get('username', 'Guest'),
                    'name': name,
                    'address': address,
                    'phone': phone,
                    'items': cart_items,
                    'total_amount': total_amount,
                    'payment_method': payment_method,
                    'timestamp': datetime.now().isoformat()
                }
            )

            # Send confirmation email
            send_email(
                to_email=session.get('email'),
                subject="Order Confirmation - VE'N'NA PICKLES",
                body=f"""
Hi {name},

Thank you for your order of ₹{total_amount:.2f}!

We’ve received the following items:
{json.dumps(cart_items, indent=2)}

Delivery Address:
{address}

We’ll notify you once it’s out for delivery.

Regards,
VE'N'NA PICKLES
                """
            )

            # Clear the cart
            session.pop('cart', None)

            return redirect(url_for('success', message="Your order has been placed successfully!"))

        except Exception as e:
            print(f"Checkout error: {str(e)}")
            return render_template('check_out.html', error="An unexpected error occurred. Please try again.")

    return render_template('check_out.html')

# Send confirmation email to customer


@app.route('/cart', methods=['GET', 'POST'])
def cart():
    if request.method == 'POST':
        if 'cart' not in session:
            session['cart'] = []

        # Fetch form data
        product_id = request.form.get('product_id')
        product_name = request.form.get('product_name')
        weight = request.form.get('weight')
        quantity = int(request.form.get('quantity', 1))

        # You may also want to store price — here’s how to get it:
        price = None
        for category in products.values():
            for item in category:
                if str(item['id']) == str(product_id):
                    price = item['weights'].get(weight)
                    break

        # Add to cart in session
        if price:
            session['cart'].append({
                'id': product_id,
                'name': product_name,
                'weight': weight,
                'price': price,
                'quantity': quantity
            })
            session.modified = True
    

    return render_template('cart.html', cart=session.get('cart', []))


@app.route('/success')
def success():
    message = request.args.get('message', 'Order placed!')
    return render_template('success.html', message=message)


@app.route('/about')
def about():
    return render_template('about.html')
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) # Add debug True temporarily
