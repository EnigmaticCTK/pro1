# pro1
Arduino Soil moisture project 

## Overview
This project is a real-time soil moisture monitoring system that combines hardware and web technologies to track environmental conditions. It reads soil moisture data using sensors connected to an Arduino and displays the data on a web-based dashboard.

The system is designed to provide real-time visualization of soil conditions using charts and a responsive interface.

---

## System Architecture

The project is divided into three main parts:

### 1. Hardware Layer
- Soil moisture sensor
- Arduino microcontroller
- C/C++ firmware to read sensor data

### 2. Communication Layer
- Python backend
- Socket.IO for real-time data transfer between hardware and frontend

### 3. Frontend Dashboard
- HTML, CSS, and JavaScript
- Tailwind CSS for styling
- Chart.js for data visualization
- Socket.IO client for real-time updates

---

## Features
- Real-time soil moisture monitoring
- Live data updates without page refresh
- Interactive charts for data visualization
- Responsive and modern UI
- Modular system design (hardware + software integration)

---

## Technologies Used
- HTML5
- CSS3
- JavaScript
- Tailwind CSS
- Chart.js
- Socket.IO
- Arduino (C/C++)
- Python (backend communication layer)

---

## How It Works
1. Soil moisture sensor collects data from soil.
2. Arduino reads sensor values using C/C++ code.
3. Data is sent to a backend server (Python/Socket.IO).
4. The web dashboard receives live updates.
5. Chart.js visualizes the data in real time.

---

## Project Structure
```text id="project-structure"
/
├── index.html
├── dashboard.html
├── css/
├── js/
├── images/
├── arduino_code/
├── backend/
└── README.md
