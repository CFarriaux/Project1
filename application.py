import os
import requests

from flask import Flask, session, render_template, jsonify, request
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from datetime import date

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

@app.route("/", methods=["GET", "POST"])
def login():
    """Show login form"""
    if request.method == "POST":
        session.pop("user_id")
        return render_template("login.html", message="You are now logged out.")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def home():
    return render_template("register.html")


@app.route("/registered", methods=["POST"])
def register():
    """Register a user"""

    # Get form information.
    username = request.form.get("username")
    password = request.form.get("password")

    # Check if username exists.
    if db.execute("SELECT * FROM users WHERE username = :username", {"username": username}).rowcount != 0:
        return render_template("register.html", message="Username is already taken.")

    # Check username and password length.
    if len(password) < 8 :
        return render_template("register.html", message="Please make sure to respect password length.")   

    # Create new user.
    db.execute("INSERT INTO users (username, password) VALUES (:username, :password)",
            {"username": username, "password": password})
    db.commit()
     
    return render_template("login.html", message="Your account was succesfully created!")

@app.route("/account", methods=["GET", "POST"])
def index():
    """Login a user and show her account"""

    if request.method == "POST":
        # Get form information.
        username = request.form.get("username")
        password = request.form.get("password")

        # Check username and password.
        if db.execute("SELECT * FROM users WHERE username = :username", {"username": username}).rowcount == 0:
            return render_template("login.html", message="Username does not exist.")
        user = db.execute("SELECT id, username, password FROM users WHERE username = :username", {"username": username}).fetchone()
        if user.password != password:
            return render_template("login.html", message="Wrong password")  

        # Save user id for this session. 
        session["user_id"] = user.id 

    if session.get("user_id") is None:
        return render_template("login.html", message="Please log in")

    user = db.execute("SELECT username FROM users WHERE id = :id", {"id": session["user_id"]}).fetchone()
    suggestions = db.execute("SELECT * FROM books ORDER BY year DESC LIMIT 12").fetchall()

    return render_template("index.html", username=user.username, suggestions=suggestions)

@app.route("/review/<int:book_id>", methods=["POST"])
def review(book_id):
    """Save a review for a book"""
    if session.get("user_id") is None:
        return render_template("login.html", message="Please log in")

    # Get form information.
    score = request.form.get("score")
    comment = request.form.get("comment")
    date_posted = date.today()
    user_id = session["user_id"]

    # Make sure book exists.
    if db.execute("SELECT * FROM books WHERE id = :id", {"id": book_id}).rowcount == 0:
        return render_template("error.html", message="No such book with that id.")
    
    # Make sure user has not posted a review yet.
    if db.execute("SELECT * FROM reviews WHERE user_id = :user_id AND book_id = :book_id", {"user_id": user_id, "book_id": book_id}).rowcount != 0:
        return render_template("error.html", message="You have already posted a review.")

    # Save review.
    db.execute("INSERT INTO reviews (score, comment, date_posted, book_id, user_id) VALUES (:score, :comment, :date_posted, :book_id, :user_id)",
            {"score": score, "comment": comment, "date_posted": date_posted, "book_id": book_id, "user_id": user_id})
    db.commit()
    return render_template("success.html", message="Your review was successful!")


@app.route("/books", methods=["POST"])
def books():
    """List all search results."""
    if session.get("user_id") is None:
        return render_template("login.html", message="Please log in")  

    # Get form information.
    query = request.form.get("query")

    # Make sure book exists.
    if db.execute("SELECT * FROM books WHERE (isbn LIKE :query) OR (title LIKE :query) OR (author LIKE :query)", { "query": '%' + query + '%'}).rowcount == 0:
        return render_template("books.html", query=query, message="No such book with that that information.")
    
    # List search results.
    books = db.execute("SELECT * FROM books WHERE (isbn LIKE :query) OR (title LIKE :query) OR (author LIKE :query) order by TITLE", { "query": '%' + query + '%'}).fetchall()
    return render_template("books.html", books=books, query=query)

@app.route("/books/<int:book_id>")
def book(book_id):
    """List details about a single book."""
    if session.get("user_id") is None:
        return render_template("login.html", message="Please log in")

    # Make sure book exists.
    book = db.execute("SELECT * FROM books WHERE id = :id", {"id": book_id}).fetchone()
    if book is None:
        return render_template("error.html", message="No such book.")

    # Get all reviews.
    reviews = db.execute("SELECT score, comment, date_posted FROM reviews WHERE book_id = :book_id", {"book_id": book_id}).fetchall()
    user = db.execute("SELECT * FROM users WHERE id IN (SELECT user_id FROM reviews WHERE book_id = :book_id)", {"book_id": book_id}).fetchone()

    # Call goodreads API.
    key = "Moy1679vGlz4o9sG2joKQ"
    isbn = db.execute("SELECT isbn FROM books WHERE id = :id", {"id": book_id}).fetchone()
    res = requests.get("https://www.goodreads.com/book/review_counts.json?",
                       params={"key": key, "isbns": isbn})
    if res.status_code != 200:
        raise Exception("ERROR: API request unsuccessful.")
    data = res.json()
    score = data["books"][0]["average_rating"]
    ratings_count = data["books"][0]["work_ratings_count"]

    return render_template("book.html", book=book, reviews=reviews, user=user, score=score, ratings_count=ratings_count)

@app.route("/api")
def api():
    """Return API description."""
    return render_template("api.html")


@app.route("/api/books/<isbn>")
def book_api(isbn):
    """Return data about a single book."""
    if session.get("user_id") is None:
        return render_template("login.html", message="Please log in")

    # Make sure book exists.
    book = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchone()
    if book is None:
        return jsonify({"error 404": "Invalid isbn"}), 404

    # Get all reviews.
    count = db.execute("SELECT count(*) FROM reviews WHERE book_id IN (SELECT book_id FROM books WHERE isbn = :isbn)",
                            {"isbn": isbn}).fetchall()
    average = db.execute("SELECT AVG(score) FROM reviews WHERE book_id IN (SELECT book_id FROM books WHERE isbn = :isbn)",
                            {"isbn": isbn}).fetchall()
 
    review_count = [dict(row) for row in count][0]["count"]
    average_score = [dict(row) for row in average][0]["avg"]

    if average_score is None:
        average_score = "N/A"
    else:
        average_score = round(average_score, 1)

    # Display data.
    return jsonify({
            "title": book.title,
            "author": book.author,
            "year": book.year,
            "isbn": book.isbn,
            "review_count": review_count,
            "average_score": average_score
        })