from flask import Flask, request, redirect, url_for, render_template, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import requests
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
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
    headers = {
        'Content-Type': 'application/json'
    }
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    try:
        response = requests.post(API_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        response_data = response.json()
        if 'candidates' in response_data and response_data['candidates']:
            generated_text = response_data['candidates'][0]['content']['parts'][0]['text']
            print("Gemini AI Response:", generated_text)
            return generated_text
        else:
            print("Unexpected API response:", response_data)
            return None
    except requests.exceptions.RequestException as e:
        print(f"API Request Error: {str(e)}")
        return None

# Routes
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Username and password are required', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('register'))
            
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.password == password:
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
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
    return render_template('dashboard.html', username=current_user.username)

@app.route('/book', methods=['POST'])
@login_required
def book():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
        
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    try:
        # Handle both direct details and nested details
        if 'details' in data and isinstance(data['details'], dict):
            details = data['details']
            details_str = f"Type: {data.get('type', 'N/A')}\n"
            details_str += f"Travel: {details.get('travel', 'N/A')}\n"
            details_str += f"Food: {details.get('food', 'N/A')}\n"
            details_str += f"Accommodation: {details.get('accommodation', 'N/A')}"
        else:
            details_str = json.dumps(data)
        
        booking = Booking(
            type=data.get('type', 'Budget Travel Plan'),
            details=details_str,
            user_id=current_user.id
        )
        db.session.add(booking)
        db.session.commit()
        return jsonify({
            "message": "Booking successful!",
            "booking_id": booking.id,
            "type": booking.type
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/cart')
@login_required
def cart():
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.date.desc()).all()
    return render_template('cart.html', bookings=bookings)

@app.route('/delete_booking/<int:booking_id>', methods=['POST'])
@login_required
def delete_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        flash('You cannot delete this booking', 'danger')
        return redirect(url_for('cart'))
    
    db.session.delete(booking)
    db.session.commit()
    flash('Booking deleted successfully', 'success')
    return redirect(url_for('cart'))

@app.route('/food', methods=['GET', 'POST'])
@login_required
def food():
    if request.method == 'POST':
        food_type = request.form.get('food_type', '').strip()
        food_name = request.form.get('food_name', '').strip()
        location = request.form.get('location', '').strip()
        
        if not all([food_type, food_name, location]):
            flash('All fields are required', 'danger')
            return redirect(url_for('food'))
        
        prompt = (
            f"Find restaurants in {location} that serve {food_type} like {food_name}. "
            "Provide names, locations, and costs in the following format:\n\n"
            "Restaurant: <name>\nLocation: <location>\nCost: <cost>\n\n"
            "Separate each restaurant with a new line. Include at least 5 options."
        )
        
        response = send_message(prompt)
        if response:
            restaurants = parse_restaurant_results(response)
            if restaurants:
                return render_template('food_results.html', 
                                    restaurants=restaurants,
                                    food_type=food_type,
                                    location=location)
            else:
                flash('No restaurants found. Please try different parameters.', 'warning')
        else:
            flash('Failed to fetch results. Please try again.', 'danger')
    return render_template('food.html')

def parse_restaurant_results(response):
    restaurants = []
    current_restaurant = {}
    
    for line in response.split('\n'):
        line = line.strip()
        if line.startswith("Restaurant:"):
            if current_restaurant:
                restaurants.append(current_restaurant)
            current_restaurant = {
                'name': line.replace("Restaurant:", "").strip(),
                'location': '',
                'cost': ''
            }
        elif line.startswith("Location:"):
            current_restaurant['location'] = line.replace("Location:", "").strip()
        elif line.startswith("Cost:"):
            current_restaurant['cost'] = line.replace("Cost:", "").strip()
    
    if current_restaurant:
        restaurants.append(current_restaurant)
    
    return restaurants[:10]  # Limit to 10 results
@app.route('/travel', methods=['GET', 'POST'])
@login_required
def travel():
    if request.method == 'POST':
        source = request.form.get('source', '').strip()
        destination = request.form.get('destination', '').strip()
        date = request.form.get('date', '').strip()
        
        # Check if date is too far in the future
        travel_date = datetime.strptime(date, '%Y-%m-%d').date()
        today = datetime.now().date()
        delta = (travel_date - today).days
        
        if delta > 180:  # More than 6 months in future
            return render_template('travel_results.html',
                                too_far_future=True,
                                source=source,
                                destination=destination,
                                date=date)
        
        # More specific prompt for dates within 6 months
        prompt = (
            f"Provide specific, bookable bus and flight options from {source} to {destination} on {date} in this exact format:\n\n"
            "**BUS OPTIONS**\n"
            "- Operator: RedBus\n"
            "  - Fare: ₹X, Duration: X hours, Departure: XX:XX AM/PM, Type: AC Sleeper\n"
            "- Operator: AbhiBus\n"
            "  - Fare: ₹X, Duration: X hours, Departure: XX:XX AM/PM, Type: Volvo AC\n\n"
            "**FLIGHT OPTIONS**\n"
            "- Airline: IndiGo\n"
            "  - Fare: ₹X, Duration: X hours, Departure: XX:XX AM/PM, Flight No: 6E-XXXX\n"
            "- Airline: Air India\n"
            "  - Fare: ₹X, Duration: X hours, Departure: XX:XX AM/PM, Flight No: AI-XXXX\n\n"
            "Only include real, bookable options with all required details."
        )
        
        response = send_message(prompt)
        
        if response and "cannot provide real-time" not in response:
            travel_options = parse_travel_results(response)
            
            if travel_options['buses'] or travel_options['flights']:
                return render_template('travel_results.html',
                                    travel_options=travel_options,
                                    source=source,
                                    destination=destination,
                                    date=date)
        
        # If no specific options found
        return render_template('travel_results.html',
                            general_info=True,
                            source=source,
                            destination=destination,
                            date=date)
    
    return render_template('travel.html')
def parse_travel_results(response):
    travel_options = {'buses': [], 'flights': []}
    current_section = None
    current_provider = None

    for line in response.split('\n'):
        line = line.strip()
        
        # Detect sections
        if line.startswith("**BUS OPTIONS**"):
            current_section = 'buses'
            continue
        elif line.startswith("**FLIGHT OPTIONS**"):
            current_section = 'flights'
            continue
            
        # Parse provider lines
        if line.startswith("- Operator:") and current_section == 'buses':
            provider = line.replace("- Operator:", "").strip()
            travel_options['buses'].append({
                'provider': provider,
                'options': []
            })
            current_provider = provider
        elif line.startswith("- Airline:") and current_section == 'flights':
            provider = line.replace("- Airline:", "").strip()
            travel_options['flights'].append({
                'provider': provider,
                'options': []
            })
            current_provider = provider
            
        # Parse option lines
        elif line.startswith("  - Fare:") and current_provider:
            option = line.replace("  - ", "").strip()
            # Add to the last provider in the current section
            if current_section == 'buses' and travel_options['buses']:
                travel_options['buses'][-1]['options'].append(option)
            elif current_section == 'flights' and travel_options['flights']:
                travel_options['flights'][-1]['options'].append(option)

    return travel_options

@app.route('/accommodation', methods=['GET', 'POST'])
@login_required
def accommodation():
    if request.method == 'POST':
        location = request.form.get('location', '').strip()
        
        if not location:
            flash('Location is required', 'danger')
            return redirect(url_for('accommodation'))
        
        prompt = (
            f"Find hotels in {location}. Provide hotel names, locations, and prices "
            "in the following format:\n\n"
            "Hotel: <name>\nLocation: <location>\nPrice: <price>\n\n"
            "Separate each hotel with a new line. Include at least 5 options."
        )
        
        response = send_message(prompt)
        if response:
            hotels = parse_accommodation_results(response)
            if hotels:
                return render_template('accommodation_results.html', 
                                    hotels=hotels,
                                    location=location)
            else:
                flash('No hotels found. Please try a different location.', 'warning')
        else:
            flash('Failed to fetch results. Please try again.', 'danger')
    return render_template('accommodation.html')

def parse_accommodation_results(response):
    hotels = []
    current_hotel = {}
    
    for line in response.split('\n'):
        line = line.strip()
        if line.startswith("Hotel:"):
            if current_hotel:
                hotels.append(current_hotel)
            current_hotel = {
                'name': line.replace("Hotel:", "").strip(),
                'location': '',
                'price': ''
            }
        elif line.startswith("Location:"):
            current_hotel['location'] = line.replace("Location:", "").strip()
        elif line.startswith("Price:"):
            current_hotel['price'] = line.replace("Price:", "").strip()
    
    if current_hotel:
        hotels.append(current_hotel)
    
    return hotels[:10]  # Limit to 10 results

@app.route('/budget', methods=['GET', 'POST'])
@login_required
def budget():
    if request.method == 'POST':
        source = request.form.get('source', '').strip()
        destination = request.form.get('destination', '').strip()
        date = request.form.get('date', '').strip()
        
        if not all([source, destination, date]):
            flash('All fields are required', 'danger')
            return redirect(url_for('budget'))
        
        prompt = (
            f"Create a detailed budget travel plan from {source} to {destination} on {date}. "
            "Provide costs for travel, food, and accommodation in three categories: "
            "Low, Medium, and Premium. Format the response with clear section headers: "
            "**Low Budget:**, **Medium Budget:**, **Premium Budget:** "
            "Each section should have - **Travel:**, - **Food:**, - **Accommodation:** subsections. "
            "Provide specific options and prices for each category."
        )
        
        response = send_message(prompt)
        if response:
            budget_plans = parse_budget_results(response)
            if budget_plans:
                return render_template('budget_results.html', 
                                    budget_plans=budget_plans,
                                    source=source,
                                    destination=destination,
                                    date=date)
            else:
                flash('No budget plans found. Please try different parameters.', 'warning')
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

    for line in response.split('\n'):
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
        if line.startswith("*   **Travel:**"):
            if current_section and current_category and content_buffer:
                budget_plans[current_category][current_section] = '\n'.join(content_buffer)
            current_section = 'travel'
            content_buffer = []
            continue
        elif line.startswith("*   **Food:**"):
            if current_section and current_category and content_buffer:
                budget_plans[current_category][current_section] = '\n'.join(content_buffer)
            current_section = 'food'
            content_buffer = []
            continue
        elif line.startswith("*   **Accommodation:**"):
            if current_section and current_category and content_buffer:
                budget_plans[current_category][current_section] = '\n'.join(content_buffer)
            current_section = 'accommodation'
            content_buffer = []
            continue
            
        # Collect content for current section
        if current_category and current_section and line:
            content_buffer.append(line)
    
    # Add the last section's content
    if current_section and current_category and content_buffer:
        budget_plans[current_category][current_section] = '\n'.join(content_buffer)

    return budget_plans
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)