import json
from flask import Flask, render_template, request, redirect, url_for, session
from flask_session import Session

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base

from argon2 import PasswordHasher

app = Flask(__name__)

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

engine = create_engine('sqlite:///scaredycat.db')
Base = declarative_base()
Base.metadata.reflect(engine)
    
@app.route('/')
def front_page():
    with engine.connect() as connection:
        results = connection.execute(text("""
            SELECT ProductImage.ImageKey, Product.Name, Product.Id, Product.Category
            FROM ProductImage, Product
            WHERE Product.Tag="new" AND ProductImage.ProductId=Product.Id AND ProductImage.Main=1
        """))

    return render_template('front_page.html', results=results)


@app.route('/register_user', methods = ['GET', 'POST'])
def register_user():
    if request.method == 'POST':
        email = request.form['register_email']

        password = request.form['register_password']
        ph = PasswordHasher()
        p_hash = ph.hash(password)

        gender = request.form['register_gender']

        try:
            with engine.connect() as connection:
                connection.execute(text(f"""
                    INSERT INTO User (Email, PassHash, Gender)
                    VALUES ("{email}", "{p_hash}", "{gender}")
                """))
                connection.commit()

                connection.execute(text(f"""
                    INSERT INTO Cart (UserId)
                    SELECT Id 
                    FROM User
                    WHERE Email="{email}"
                """))
                connection.commit()

                with engine.connect() as connection:
                    result = list(connection.execute(text(f"""
                        SELECT User.Id, Cart.Id
                        FROM User, Cart
                        WHERE User.Email="{email}"
                    """)))

                    session["id"] = result[0][0]
                    session["cart_id"] = result[0][1]
                    session['basket'] = []

            return redirect(url_for('front_page'))
        
        except: #email in use
            return redirect(url_for('front_page'))
    

@app.route('/login_user', methods = ['GET', 'POST'])
def login_user():
    if request.method == 'POST':
        email = request.form['login_email']
        password = request.form['login_password']

        try:
            with engine.connect() as connection:
                result = list(connection.execute(text(f"""
                    SELECT PassHash, Id
                    FROM User
                    WHERE Email="{email}"
                """)))

            hash = result[0][0]
            ph = PasswordHasher()

            if ph.verify(hash, password):
                session["id"] = result[0][1]

                #session['basket'] get basket from database
                with engine.connect() as connection:
                    session['cart_id'] = list(connection.execute(text(f"""
                        SELECT Id
                        FROM Cart
                        WHERE UserId={session['id']}
                    """)))[0][0]

                    session['basket'] = list(connection.execute(text(f"""
                        SELECT ProductId, Size, Quantity
                        FROM CartItem
                        WHERE CartId={session['cart_id']}
                    """)))

                return redirect(url_for('front_page'))
            else: #password incorrect
                return redirect(url_for('front_page'))
                

        except:#no account with email
            return redirect(url_for('front_page'))


@app.route('/logout_user', methods = ['GET', 'POST'])
def logout_user():
    if request.method == 'POST':
        del session['id']
        del session['cart_id']
        session['basket'] = []
        return redirect(url_for('front_page'))


@app.route('/<string:product_type>_page', methods = ['GET', 'POST'])
def products_page(product_type):
    if request.method == 'POST':
        session['order_preference'] = request.form['order']
        return redirect(url_for('products_page', product_type=product_type))
    else:
        sql = ""
        if product_type == "shirts":
            sql = "AND Product.Category='shirt'"
        elif product_type == "prints":
            sql = "AND Product.Category='print'"
        elif product_type == "all":
            sql = ""

        if not session.get('order_preference'):
            session['order_preference'] = "alphabetical_forward"

        order_by = ""
        if session['order_preference'] == "alphabetical_forward":
            order_by = "ORDER BY Product.Name ASC"
        elif session['order_preference'] == "alphabetical_backward":
            order_by = "ORDER BY Product.Name DESC"
        elif session['order_preference'] == "price_lowest":
            order_by = "ORDER BY Product.Price ASC"
        elif session['order_preference'] == "price_highest":
            order_by = "ORDER BY Product.Price DESC"
        elif session['order_preference'] == "carbon_footprint":
            order_by = "ORDER BY Product.CarbonFootprint ASC"
        else:
            pass

        with engine.connect() as connection:
            products = connection.execute(text(f"""
                SELECT ProductImage.ImageKey, Product.Name, Product.Price, Product.Id
                FROM ProductImage, Product
                WHERE ProductImage.ProductId=Product.Id AND ProductImage.Main=1 {sql}
                {order_by}
            """))
        return render_template('products_page.html', product_type=product_type, products=products)
    

@app.route('/product_<int:id>', methods = ['GET', 'POST'])
def product_page(id):
    if request.method == 'POST':
        id = request.form['id']
        return redirect(url_for('product_page',id=id))
    else:
        with engine.connect() as connection:
            data = connection.execute(text(f"""
                SELECT Name, Price, Description, Category, CarbonFootprint
                FROM Product
                WHERE Id={id}
            """))

            images = connection.execute(text(f"""
                SELECT ImageKey, Description, Main
                FROM ProductImage
                WHERE productId={id}
            """))

        return render_template('product_page.html',id=id, data=list(data), images=list(images))


@app.route('/add_to_basket', methods = ['GET', 'POST'])
def add_to_basket():
    if not session.get('basket'):
        session['basket'] = []

    id = request.form['item_id']
    size = request.form['size']
    quantity = request.form['item_quantity']

    session['basket'].append([id, size, quantity])

    #if user is logged in
    if session.get('id'):
        with engine.connect() as connection:
            connection.execute(text(f"""
                INSERT INTO CartItem (CartId, ProductId, Size, Quantity)
                VALUES ("{session['cart_id']}", "{id}", "{size}", "{quantity}")
            """))
            connection.commit()

    return redirect(url_for('product_page', id=id))


@app.route('/account')
def account_page(): 
    with engine.connect() as connection:
        data = connection.execute(text(f"""
            SELECT Email, Gender
            FROM User
            WHERE Id={session['id']}
        """))
        
    return render_template('account_page.html', data=list(data)[0])


@app.route('/basket', methods = ['GET', 'POST'])
def basket_page():
    if not session.get('basket'):
        session['basket'] = []

    if request.method == 'POST':
        name = request.form['card_name']
        serialised = str(session['basket'])

        with engine.connect() as connection:
            connection.execute(text(f"""
                INSERT INTO UserOrder (Name, Serialised)
                VALUES ("{name}", "{serialised}")
            """))
            connection.commit()

        session['basket'] = []
        return(redirect(url_for("basket_page")))
    else:
        with engine.connect() as connection:
            subtotal = 0
            basket = []
            for item in session['basket']:
                data = list(connection.execute(text(f"""
                    SELECT Product.Name, Product.Price, ProductImage.ImageKey, Product.Category
                    FROM Product
                    INNER JOIN ProductImage ON Product.Id=ProductImage.ProductId
                    WHERE ProductImage.Main=1 AND Product.Id={item[0]}
                """)))
                basket.append(list(item) + list(data[0]))
                subtotal += round(list(data[0])[1] * int(list(item)[2]), 2)
            
        return render_template('basket_page.html', basket=basket, subtotal=subtotal)
    

@app.route('/delete_cart_item', methods = ['GET', 'POST'])
def delete_cart_item():
    if request.method == 'POST':

        if session.get('id'):
            item_id = request.form['item_id']

            with engine.connect() as connection:
                connection.execute(text(f"""
                    DELETE FROM CartItem
                    WHERE ProductId={item_id} AND CartId={session['cart_id']}
                """))
                connection.commit()
        
        item_index = int(request.form['item_index'])
        session['basket'].pop(item_index)

        return redirect(url_for('basket_page'))
    

@app.route('/minus_cart_item', methods = ['GET', 'POST'])
def minus_cart_item():
    if request.method == 'POST':

        item_index = int(request.form['item_index'])
        quantity = int(session['basket'][item_index][2])
        
        if quantity > 1:
            session['basket'][item_index][2] = quantity - 1

            if session.get('id'):
                item_id = request.form['item_id']

                with engine.connect() as connection:
                    connection.execute(text(f"""
                        UPDATE CartItem
                        SET Quantity = Quantity - 1
                        WHERE ProductId={item_id} AND CartId={session['cart_id']}
                    """))
                    connection.commit()

        return redirect(url_for('basket_page'))
    

@app.route('/add_cart_item', methods = ['GET', 'POST'])
def add_cart_item():
    if request.method == 'POST':

        item_index = int(request.form['item_index'])
        quantity = int(session['basket'][item_index][2])

        if quantity < 9:
            session['basket'][item_index][2] = quantity + 1

            if session.get('id'):
                item_id = request.form['item_id']

                with engine.connect() as connection:
                    connection.execute(text(f"""
                        UPDATE CartItem
                        SET Quantity = Quantity + 1
                        WHERE ProductId={item_id} AND CartId={session['cart_id']}
                    """))
                    connection.commit()

        return redirect(url_for('basket_page'))
    

@app.route('/search', methods = ['GET', 'POST'])
def search():
    if request.method == 'POST':
        search_word = request.form['search_input']

        with engine.connect() as connection:
            results = list(connection.execute(text(f"""
                SELECT Id
                FROM Product
                WHERE Name LIKE '%{search_word}%'
            """)))[0][0]

        return redirect(url_for('product_page', id=results))


if __name__ == "__main__":
    app.run(debug=True)