from flask import Flask, request, redirect, url_for, render_template, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import requests
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

API_KEY = 'AIzaSyD3MJxDBQHPjHI1PSRj5FJifr6U9pn3J6w'
API_URL = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    bookings = db.relationship('Booking', backref='user', lazy=True)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)
    details = db.Column(db.String(500), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Helper function to interact with Gemini API
def send_message(prompt):
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    response = requests.post(API_URL, json=data)
    if response.status_code == 200:
        response_data = response.json()
        generated_text = response_data['candidates'][0]['content']['parts'][0]['text']
        print("Gemini AI Response:", generated_text)  # Debugging
        return generated_text
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None
# Routes
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Login Unsuccessful. Please check username and password', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/book', methods=['POST'])
@login_required
def book():
    data = request.json
    booking = Booking(
        type=data['type'],
        details=f"Restaurant: {data['name']}, Location: {data['location']}, Cost: {data['cost']}",
        user_id=current_user.id
    )
    db.session.add(booking)
    db.session.commit()
    return jsonify({"message": "Booking successful!"})

@app.route('/cart')
@login_required
def cart():
    bookings = Booking.query.filter_by(user_id=current_user.id).all()
    return render_template('cart.html', bookings=bookings)

@app.route('/food', methods=['GET', 'POST'])
@login_required
def food():
    if request.method == 'POST':
        food_type = request.form['food_type']
        food_name = request.form['food_name']
        location = request.form['location']
        
        # Create a prompt for Gemini AI
        prompt = f"Find restaurants in {location} that serve {food_type} like {food_name}. Provide names, locations, and costs in the following format:\n\nRestaurant: <name>\nLocation: <location>\nCost: <cost>\n\nSeparate each restaurant with a new line."
        
        # Fetch results from Gemini AI
        response = send_message(prompt)
        if response:
            # Parse the response into multiple restaurant results
            restaurants = parse_restaurant_results(response)
            if restaurants:
                return render_template('food_results.html', restaurants=restaurants)
            else:
                flash('No restaurants found. Please try again.', 'danger')
        else:
            flash('Failed to fetch results. Please try again.', 'danger')
    return render_template('food.html')

def parse_restaurant_results(response):
    # Initialize variables
    restaurants = []
    current_restaurant = {}

    # Split the response into lines
    lines = response.split('\n')

    for line in lines:
        line = line.strip()  # Remove leading/trailing whitespace
        if line.startswith("Restaurant:"):
            # If we already have a restaurant, add it to the list
            if current_restaurant:
                restaurants.append(current_restaurant)
                current_restaurant = {}
            current_restaurant['name'] = line.split("Restaurant:")[1].strip()
        elif line.startswith("Location:"):
            current_restaurant['location'] = line.split("Location:")[1].strip()
        elif line.startswith("Cost:"):
            current_restaurant['cost'] = line.split("Cost:")[1].strip()

    # Add the last restaurant if it exists
    if current_restaurant:
        restaurants.append(current_restaurant)

    return restaurants

# Travel Route
@app.route('/travel', methods=['GET', 'POST'])
@login_required
def travel():
    if request.method == 'POST':
        source = request.form['source']
        destination = request.form['destination']
        date = request.form['date']
        
        #prompt = f"Find bus and flight options from {source} to {destination} on {date}. Provide details for buses (RedBus, AbhiBus) and flights (MakeMyTrip) in the following format:\n\nBus:\n- RedBus: <details>\n- AbhiBus: <details>\n\nFlight:\n- MakeMyTrip: <details>\n\nInclude fare and duration for each option."
        prompt = f"Find bus and flight options from {source} to {destination} on {date}. Provide details for buses (RedBus, AbhiBus) and flights (MakeMyTrip) in the following format:\n\nBus:\n- RedBus: Fare: <fare>, Duration: <duration>\n- AbhiBus: Fare: <fare>, Duration: <duration>\n\nFlight:\n- MakeMyTrip: Fare: <fare>, Duration: <duration>\n\nInclude fare and duration for each option."
        response = send_message(prompt)
        if response:
            travel_options = parse_travel_results(response)
            print("Travel Options to Template:", travel_options)  # Debugging
            if travel_options:
                return render_template('travel_results.html', travel_options=travel_options)
            else:
                flash('No travel options found. Please try again.', 'danger')
        else:
            flash('Failed to fetch results. Please try again.', 'danger')
    return render_template('travel.html')

def parse_travel_results(response):
    print("Parsing Travel Results...")  # Debugging
    travel_options = {
        'buses': [],
        'flights': []
    }

    # Extract the relevant part of the response
    start_marker = "**Bus:**"
    end_marker = "**Flight:**"
    start_index = response.find(start_marker)
    end_index = response.find(end_marker)

    if start_index == -1:
        print("Error: Could not find bus start marker in response.")
    if end_index == -1:
        print("Error: Could not find flight start marker in response.")
    if start_index == -1 or end_index == -1:
        return travel_options

    # Extract bus and flight sections safely
    bus_section = response[start_index:end_index].strip()
    flight_section = response[end_index:].strip()

    print("Bus Section:", bus_section)  # Debugging
    print("Flight Section:", flight_section)  # Debugging

    # Parse bus options using more flexible checks
    for line in bus_section.split('\n'):
        line = line.strip()
        if line.startswith("* ") and ':' in line:
            provider, details = map(str.strip, line.split(':', 1))
            provider = provider.replace('*', '').strip()
            print(f"Adding bus: {provider} - {details}")  # Debugging
            travel_options['buses'].append({
                'provider': provider,
                'details': details
            })

    # Parse flight options
    for line in flight_section.split('\n'):
        line = line.strip()
        if line.startswith("* ") and ':' in line:
            provider, details = map(str.strip, line.split(':', 1))
            provider = provider.replace('*', '').strip()
            print(f"Adding flight: {provider} - {details}")  # Debugging
            travel_options['flights'].append({
                'provider': provider,
                'details': details
            })

    print("Parsed Travel Options:", travel_options)  # Debugging
    return travel_options


# Accommodation Route
@app.route('/accommodation', methods=['GET', 'POST'])
@login_required
def accommodation():
    if request.method == 'POST':
        location = request.form['location']
        
        # Create a prompt for Gemini AI
        prompt = f"Find hotels in {location}. Provide hotel names, locations, and prices in the following format:\n\nHotel: <name>\nLocation: <location>\nPrice: <price>\n\nSeparate each hotel with a new line."
        
        # Fetch results from Gemini AI
        response = send_message(prompt)
        if response:
            # Parse the response into multiple hotel options
            hotels = parse_accommodation_results(response)
            if hotels:
                return render_template('accommodation_results.html', hotels=hotels)
            else:
                flash('No hotels found. Please try again.', 'danger')
        else:
            flash('Failed to fetch results. Please try again.', 'danger')
    return render_template('accommodation.html')

def parse_accommodation_results(response):
    # Initialize variables
    hotels = []

    # Split the response into lines
    lines = response.split('\n')

    for line in lines:
        line = line.strip()  # Remove leading/trailing whitespace
        if line.startswith("Hotel:"):
            hotel = {
                'name': line.split("Hotel:")[1].strip()
            }
        elif line.startswith("Location:"):
            hotel['location'] = line.split("Location:")[1].strip()
        elif line.startswith("Price:"):
            hotel['price'] = line.split("Price:")[1].strip()
            hotels.append(hotel)

    return hotels


@app.route('/budget', methods=['GET', 'POST'])
@login_required
def budget():
    if request.method == 'POST':
        source = request.form['source']
        destination = request.form['destination']
        date = request.form['date']
        
        prompt = f"Create a detailed budget travel plan from {source} to {destination} on {date}. "\
                 "Provide costs for travel, food, and accommodation in three categories: "\
                 "Low, Medium, and Premium. Format the response with clear section headers: "\
                 "**Low Budget:**, **Medium Budget:**, **Premium Budget:** "\
                 "Each section should have - **Travel:**, - **Food:**, - **Accommodation:** subsections."
        
        response = send_message(prompt)
        if response:
            budget_plans = parse_budget_results(response)
            print("Parsed Budget Plans:", budget_plans)  # Debugging
            if budget_plans:
                return render_template('budget_results.html', budget_plans=budget_plans)
            else:
                flash('No budget plans found. Please try again.', 'danger')
        else:
            flash('Failed to fetch results. Please try again.', 'danger')
    return render_template('budget.html')
def parse_budget_results(response):
    budget_plans = {
        'low': {'travel': '', 'food': '', 'accommodation': ''},
        'medium': {'travel': '', 'food': '', 'accommodation': ''},
        'premium': {'travel': '', 'food': '', 'accommodation': ''}
    }

    current_category = None
    current_section = None
    content_buffer = []

    lines = response.split('\n')

    for line in lines:
        line = line.strip()
        
        # Detect budget category
        if line.startswith("**Low Budget:**"):
            current_category = 'low'
            continue
        elif line.startswith("**Medium Budget:**"):
            current_category = 'medium'
            continue
        elif line.startswith("**Premium Budget:**"):
            current_category = 'premium'
            continue
            
        # Detect section within budget category
        if line.startswith("- **Travel:**"):
            if current_section and current_category and content_buffer:
                budget_plans[current_category][current_section] = '\n'.join(content_buffer).strip()
            current_section = 'travel'
            content_buffer = []
            continue
        elif line.startswith("- **Food:**"):
            if current_section and current_category and content_buffer:
                budget_plans[current_category][current_section] = '\n'.join(content_buffer).strip()
            current_section = 'food'
            content_buffer = []
            continue
        elif line.startswith("- **Accommodation:**"):
            if current_section and current_category and content_buffer:
                budget_plans[current_category][current_section] = '\n'.join(content_buffer).strip()
            current_section = 'accommodation'
            content_buffer = []
            continue
            
        # Collect content for current section (skip empty lines and section headers)
        if current_category and current_section and line and not line.startswith("**"):
            content_buffer.append(line)
    
    # Add the last section's content
    if current_section and current_category and content_buffer:
        budget_plans[current_category][current_section] = '\n'.join(content_buffer).strip()

    return budget_plans

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)