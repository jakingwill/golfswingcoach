import os
import subprocess
import google.generativeai as genai
import requests
from flask import Flask, request, jsonify
from threading import Thread
import cv2

app = Flask(__name__)

# Initialize Gemini API client with your API key
gemini_api_key = os.environ['GEMINI_API_KEY']
client = genai.configure(api_key=gemini_api_key)
airtable_webhook_url = os.environ['AIRTABLE_WEBHOOK']

# Define functions to upload image files to Gemini
def upload_image_to_gemini(image_file_path):
    with open(image_file_path, 'rb') as file:
        response = genai.upload_file(image_file_path)
    return response.uri

# Define function to extract frames from video
def extract_video_frames(video_path, output_dir, frame_interval=10):
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    count = 0
    frame_count = 0
    success = True
    frame_paths = []

    while success:
        success, frame = cap.read()
        if success and count % frame_interval == 0:
            frame_path = os.path.join(output_dir, f'frame_{frame_count:04d}.jpg')
            cv2.imwrite(frame_path, frame)
            frame_paths.append(frame_path)
            frame_count += 1
        count += 1
    cap.release()
    return frame_paths

# Define function to upload extracted frames to Gemini
def upload_frames_to_gemini(frame_paths):
    files = []
    for frame_path in frame_paths:
        image_gemini_file = upload_image_to_gemini(frame_path)
        files.append(image_gemini_file)
    return files

# Define function to generate golf swing analysis using Gemini
def analyze_golf_swing(files, custom_prompt):
    prompt = [custom_prompt]
    prompt.extend(files)
    prompt.append("[END]\n\nHere is the golf swing video")

    model = genai.GenerativeModel(model_name='gemini-1.5-flash')
    response = model.generate_content(prompt)

    return response.text

def send_to_airtable(record_id, analysis):
    webhook_url = airtable_webhook_url
    data = {
        "record_id": record_id,
        "analysis": analysis
    }
    response = requests.post(webhook_url, json=data)
    if response.status_code == 200:
        print("Successfully sent data to Airtable")
    else:
        print(f"Failed to send data to Airtable: {response.status_code}, {response.text}")

# Function to process the video asynchronously
def process_video_async(video_path, record_id, custom_prompt):
    def process():
        try:
            print(f"Received video_url: {video_path}")
            print(f"Received record_id: {record_id}")
            print(f"Received custom_prompt: {custom_prompt}")

            # Create an 'output' directory if it doesn't exist
            output_dir = 'output'
            os.makedirs(output_dir, exist_ok=True)

            # Extract frames from the video
            frame_paths = extract_video_frames(video_path, output_dir, frame_interval=10)
            print(f"Extracted frames: {frame_paths}")

            # Upload extracted frames to Gemini
            files = upload_frames_to_gemini(frame_paths)
            print(f"Uploaded frames to Gemini: {files}")

            # Generate golf swing analysis using Gemini
            analysis = analyze_golf_swing(files, custom_prompt)
            print(f"Analysis: {analysis}")

            # Send analysis to Airtable
            send_to_airtable(record_id, analysis)
        except Exception as e:
            print(f"An error occurred during processing: {e}")

    # Start a new thread to process the video
    thread = Thread(target=process)
    thread.start()

@app.route('/process_video', methods=['POST'])
def process_video_route():
    data = request.get_json()
    print(f"Received data: {data}")
    video_path = data.get('video_path')
    record_id = data.get('record_id')
    custom_prompt = data.get('custom_prompt')

    if not video_path:
        print("Missing video_path")
    if not record_id:
        print("Missing record_id")

    if video_path and record_id:
        process_video_async(video_path, record_id, custom_prompt)
        return jsonify({"status": "processing started"}), 200
    else:
        return jsonify({"error": "Missing video_path or record_id"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
