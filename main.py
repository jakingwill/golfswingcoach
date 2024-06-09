import os
import subprocess
import google.generativeai as genai
import requests
from flask import Flask, request, jsonify
from threading import Thread
import cv2
from dotenv import load_dotenv
import traceback

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Initialize Gemini API client with your API key
gemini_api_key = os.getenv('GEMINI_API_KEY')
client = genai.configure(api_key=gemini_api_key)
airtable_webhook_url = os.getenv('AIRTABLE_WEBHOOK')

# Define functions to upload image files to Gemini
def upload_image_to_gemini(image_file_path):
    with open(image_file_path, 'rb') as file:
        response = genai.upload_file(image_file_path)
    return response.uri

# Define function to download video
def download_video(video_url, video_path):
    try:
        response = requests.get(video_url)
        response.raise_for_status()
        with open(video_path, 'wb') as file:
            file.write(response.content)
        return True
    except Exception as e:
        print(f"Failed to download video: {e}")
        traceback.print_exc()
        return False

# Define function to extract frames from video
def extract_video_frames(video_path, output_dir, frame_rate=1):
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    count = 0
    success = True
    while success:
        success, frame = cap.read()
        if count % frame_rate == 0 and success:
            frame_path = os.path.join(output_dir, f'frame_{count:04d}.jpg')
            cv2.imwrite(frame_path, frame)
        count += 1
    cap.release()
    return output_dir

# Define function to upload extracted frames to Gemini
def upload_frames_to_gemini(output_dir):
    files = []
    for filename in sorted(os.listdir(output_dir)):
        if filename.endswith('.jpg'):
            image_file_path = os.path.join(output_dir, filename)
            image_gemini_file = upload_image_to_gemini(image_file_path)
            files.append(image_gemini_file)
    return files

# Define function to generate golf swing analysis using Gemini
def analyze_golf_swing(files, custom_prompt):
    prompt = [custom_prompt]
    prompt.extend(files)
    prompt.append("[END]\n\nHere is the golf swing analysis")

    model = genai.GenerativeModel(model_name='gemini-1.5-flash')
    response = model.generate_content(prompt)
    print("Response from Gemini:", response.text)  # Added logging

    return response.text

def send_to_airtable(record_id, analysis):
    webhook_url = airtable_webhook_url
    data = {
        "record_id": record_id,
        "analysis": analysis
    }
    print("Sending to Airtable:", data)  # Added logging
    response = requests.post(webhook_url, json=data)
    if response.status_code == 200:
        print("Successfully sent data to Airtable")
    else:
        print(f"Failed to send data to Airtable: {response.status_code}, {response.text}")

# Function to process the video asynchronously
def process_video_async(video_url, record_id, custom_prompt):
    def process():
        try:
            print(f"Received video_url: {video_url}")
            print(f"Received record_id: {record_id}")
            print(f"Received custom_prompt: {custom_prompt}")

            # Download the video
            video_path = 'temp_video.mp4'
            if not download_video(video_url, video_path):
                print(f"Failed to download video for record ID: {record_id}")
                return

            # Create an 'output' directory if it doesn't exist
            output_dir = 'output'
            os.makedirs(output_dir, exist_ok=True)

            # Extract frames from the video
            frames_dir = extract_video_frames(video_path, output_dir)

            # Upload extracted frames to Gemini
            files = upload_frames_to_gemini(frames_dir)

            # Generate golf swing analysis using Gemini
            analysis = analyze_golf_swing(files, custom_prompt)
            print("Analysis result:", analysis)  # Added logging

            # Send analysis to Airtable
            send_to_airtable(record_id, analysis)
        except Exception as e:
            print(f"An error occurred during processing: {e}")
            traceback.print_exc()

    # Start a new thread to process the video
    thread = Thread(target=process)
    thread.start()

@app.route('/process_video', methods=['POST'])
def process_video_route():
    data = request.get_json()
    print(f"Received data: {data}")
    video_url = data.get('video_path')
    record_id = data.get('record_id')
    custom_prompt = data.get('custom_prompt')

    if not video_url:
        print("Missing video_url")
    if not record_id:
        print("Missing record_id")

    if video_url and record_id:
        process_video_async(video_url, record_id, custom_prompt)
        return jsonify({"status": "processing started"}), 200
    else:
        return jsonify({"error": "Missing video_url or record_id"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
