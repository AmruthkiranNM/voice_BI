-- ============================================================
-- Sample Database Schema for Agentic AI BI System
-- Contains: sales, customers, products, regions, orders
-- ============================================================

-- Customers table
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    join_date DATE NOT NULL
);

-- Products table
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL,
    stock_quantity INTEGER DEFAULT 0
);

-- Regions table
CREATE TABLE IF NOT EXISTS regions (
    region_id INTEGER PRIMARY KEY AUTOINCREMENT,
    region_name TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL
);

-- Orders table
CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    order_date DATE NOT NULL,
    total_amount REAL NOT NULL,
    status TEXT DEFAULT 'completed',
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

-- Sales table (line items for orders)
CREATE TABLE IF NOT EXISTS sales (
    sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    total_price REAL NOT NULL,
    sale_date DATE NOT NULL,
    region_id INTEGER,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);

-- ============================================================
-- Sample Data
-- ============================================================

-- Regions
INSERT INTO regions (region_name, city, state) VALUES
('South', 'Bangalore', 'Karnataka'),
('South', 'Chennai', 'Tamil Nadu'),
('South', 'Hyderabad', 'Telangana'),
('West', 'Mumbai', 'Maharashtra'),
('West', 'Pune', 'Maharashtra'),
('North', 'Delhi', 'Delhi'),
('North', 'Jaipur', 'Rajasthan'),
('East', 'Kolkata', 'West Bengal');

-- Customers
INSERT INTO customers (name, email, phone, city, state, join_date) VALUES
('Rahul Sharma', 'rahul@email.com', '9876543210', 'Bangalore', 'Karnataka', '2024-01-15'),
('Priya Patel', 'priya@email.com', '9876543211', 'Mumbai', 'Maharashtra', '2024-02-20'),
('Amit Kumar', 'amit@email.com', '9876543212', 'Delhi', 'Delhi', '2024-03-10'),
('Sneha Reddy', 'sneha@email.com', '9876543213', 'Hyderabad', 'Telangana', '2024-01-25'),
('Vikram Singh', 'vikram@email.com', '9876543214', 'Jaipur', 'Rajasthan', '2024-04-05'),
('Ananya Das', 'ananya@email.com', '9876543215', 'Kolkata', 'West Bengal', '2024-02-14'),
('Karthik Nair', 'karthik@email.com', '9876543216', 'Chennai', 'Tamil Nadu', '2024-05-01'),
('Deepa Gupta', 'deepa@email.com', '9876543217', 'Pune', 'Maharashtra', '2024-03-22'),
('Rajesh Iyer', 'rajesh@email.com', '9876543218', 'Bangalore', 'Karnataka', '2024-06-10'),
('Meera Joshi', 'meera@email.com', '9876543219', 'Mumbai', 'Maharashtra', '2024-04-18');

-- Products
INSERT INTO products (product_name, category, price, stock_quantity) VALUES
('Laptop Pro', 'Electronics', 75000.00, 50),
('Wireless Mouse', 'Electronics', 1500.00, 200),
('Office Chair', 'Furniture', 12000.00, 75),
('Standing Desk', 'Furniture', 25000.00, 30),
('Monitor 27"', 'Electronics', 22000.00, 100),
('Keyboard Mechanical', 'Electronics', 3500.00, 150),
('Webcam HD', 'Electronics', 4000.00, 80),
('Desk Lamp', 'Furniture', 2500.00, 120),
('USB Hub', 'Electronics', 1800.00, 200),
('Notebook Pack', 'Stationery', 500.00, 500);

-- Orders  (spanning Jan 2025 to April 2026)
INSERT INTO orders (customer_id, order_date, total_amount, status) VALUES
(1, '2025-01-15', 76500.00, 'completed'),
(2, '2025-01-22', 25000.00, 'completed'),
(3, '2025-02-10', 45500.00, 'completed'),
(4, '2025-02-18', 3500.00, 'completed'),
(5, '2025-03-05', 75000.00, 'completed'),
(6, '2025-03-20', 14500.00, 'completed'),
(7, '2025-04-01', 22000.00, 'completed'),
(8, '2025-04-15', 27500.00, 'completed'),
(9, '2025-05-10', 150000.00, 'completed'),
(10, '2025-05-25', 9000.00, 'completed'),
(1, '2025-06-12', 4000.00, 'completed'),
(2, '2025-07-08', 51500.00, 'completed'),
(3, '2025-08-14', 12000.00, 'completed'),
(4, '2025-09-03', 76500.00, 'completed'),
(5, '2025-10-18', 25500.00, 'completed'),
(6, '2025-11-22', 97000.00, 'completed'),
(7, '2025-12-10', 37500.00, 'completed'),
(8, '2026-01-15', 22000.00, 'completed'),
(9, '2026-02-20', 150500.00, 'completed'),
(10, '2026-03-10', 76500.00, 'completed'),
(1, '2026-03-25', 25000.00, 'completed'),
(2, '2026-04-05', 44000.00, 'completed'),
(3, '2026-04-12', 3500.00, 'completed');

-- Sales (line items)
INSERT INTO sales (order_id, product_id, quantity, unit_price, total_price, sale_date, region_id) VALUES
(1, 1, 1, 75000, 75000, '2025-01-15', 1),
(1, 2, 1, 1500, 1500, '2025-01-15', 1),
(2, 4, 1, 25000, 25000, '2025-01-22', 4),
(3, 5, 1, 22000, 22000, '2025-02-10', 6),
(3, 6, 1, 3500, 3500, '2025-02-10', 6),
(3, 3, 1, 12000, 12000, '2025-02-10', 6),
(3, 9, 1, 1800, 1800, '2025-02-10', 6),
(4, 6, 1, 3500, 3500, '2025-02-18', 3),
(5, 1, 1, 75000, 75000, '2025-03-05', 7),
(6, 3, 1, 12000, 12000, '2025-03-20', 8),
(6, 8, 1, 2500, 2500, '2025-03-20', 8),
(7, 5, 1, 22000, 22000, '2025-04-01', 2),
(8, 4, 1, 25000, 25000, '2025-04-15', 5),
(8, 8, 1, 2500, 2500, '2025-04-15', 5),
(9, 1, 2, 75000, 150000, '2025-05-10', 1),
(10, 7, 1, 4000, 4000, '2025-05-25', 4),
(10, 10, 10, 500, 5000, '2025-05-25', 4),
(11, 7, 1, 4000, 4000, '2025-06-12', 1),
(12, 1, 1, 75000, 75000, '2025-07-08', 4),
(12, 2, 1, 1500, 1500, '2025-07-08', 4),
(13, 3, 1, 12000, 12000, '2025-08-14', 6),
(14, 1, 1, 75000, 75000, '2025-09-03', 3),
(14, 2, 1, 1500, 1500, '2025-09-03', 3),
(15, 4, 1, 25000, 25000, '2025-10-18', 7),
(15, 10, 1, 500, 500, '2025-10-18', 7),
(16, 1, 1, 75000, 75000, '2025-11-22', 8),
(16, 5, 1, 22000, 22000, '2025-11-22', 8),
(17, 6, 5, 3500, 17500, '2025-12-10', 2),
(17, 5, 1, 22000, 22000, '2025-12-10', 2),
(18, 5, 1, 22000, 22000, '2026-01-15', 5),
(19, 1, 2, 75000, 150000, '2026-02-20', 1),
(19, 10, 1, 500, 500, '2026-02-20', 1),
(20, 1, 1, 75000, 75000, '2026-03-10', 4),
(20, 2, 1, 1500, 1500, '2026-03-10', 4),
(21, 4, 1, 25000, 25000, '2026-03-25', 1),
(22, 5, 2, 22000, 44000, '2026-04-05', 4),
(23, 6, 1, 3500, 3500, '2026-04-12', 6);
