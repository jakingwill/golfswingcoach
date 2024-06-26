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
def extract_video_frames(video_path, output_dir, frame_rate=10):  # Extract every 10th frame
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    count = 0
    success = True
    frames = []
    while success:
        success, frame = cap.read()
        if count % frame_rate == 0 and success:
            frame_path = os.path.join(output_dir, f'frame_{count:04d}.jpg')
            cv2.imwrite(frame_path, frame)
            frames.append(frame_path)
        count += 1
    cap.release()
    print(f"Extracted frames: {frames}")
    return frames

# Define function to upload extracted frames to Gemini
def upload_to_gemini(output_dir):
    files = []
    for filename in sorted(os.listdir(output_dir)):
        if filename.startswith('frame_'):
            image_file_path = os.path.join(output_dir, filename)
            image_gemini_file = upload_image_to_gemini(image_file_path)
            files.append(image_gemini_file)
    return files

# Define function to summarize content using Gemini
def summarize_content(files, custom_prompt):
    # Prepare prompt with text and image references
    prompt = [custom_prompt]
    prompt.extend(files)
    prompt.append("[END]\n\nHere are the images of the golf swing")

    # Generate content using Gemini
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
def process_video_async(video_url, record_id, custom_prompt):
    def process():
        try:
            print(f"Received video_url: {video_url}")
            print(f"Received record_id: {record_id}")
            print(f"Received custom_prompt: {custom_prompt}")

            # Create a 'downloads' directory if it doesn't exist
            os.makedirs('downloads', exist_ok=True)

            # Download video from the provided URL
            video_path = os.path.join('downloads', 'downloaded_video.mp4')
            response = requests.get(video_url)
            if response.status_code == 200:
                with open(video_path, 'wb') as file:
                    file.write(response.content)
            else:
                raise Exception(f"Failed to download video, status code: {response.status_code}")

            # Extract frames from the downloaded video
            output_dir = 'output'
            frames = extract_video_frames(video_path, output_dir)

            if frames:
                # Upload extracted frames to Gemini
                files = upload_to_gemini(output_dir)

                # Generate golf swing analysis using Gemini
                analysis = summarize_content(files, custom_prompt)
                print(f"Analysis result: {analysis}")

                # Send analysis to Airtable
                send_to_airtable(record_id, analysis)
            else:
                print("Frame extraction failed. Please check the video file.")
        except Exception as e:
            print(f"An error occurred during processing: {e}")

    # Start a new thread to process the video
    thread = Thread(target=process)
    thread.start()

@app.route('/process_video', methods=['POST'])
def process_video_route():
    data = request.get_json()
    print(f"Received data: {data}")
    video_url = data.get('video_url')
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
