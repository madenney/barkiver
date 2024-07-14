import os
import sys
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

max_workers = 8

def convert_video(input_file, output_file):
    args = [
        "ffmpeg",
        "-i", input_file,
        "-video_track_timescale", "90000",
        output_file
    ]
    #print(f"Running command: ffmpeg {' '.join(args[1:])}")
    process = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return process.returncode, input_file

def create_converted_folder(directory):
    converted_dir = os.path.join(directory, 'converted')
    if not os.path.exists(converted_dir):
        os.makedirs(converted_dir)
    return converted_dir

def main(input_directory):
    # Create the converted directory
    converted_dir = create_converted_folder(input_directory)
    
    # Get list of MP4 files in the input directory
    mp4_files = [f for f in os.listdir(input_directory) if f.endswith('.mp4')]
    
    # Use ThreadPoolExecutor to process files concurrently
    with ThreadPoolExecutor(max_workers) as executor:
        future_to_mp4 = {
            executor.submit(convert_video, os.path.join(input_directory, mp4), os.path.join(converted_dir, mp4)): mp4
            for mp4 in mp4_files
        }
        
        count = 1
        for future in as_completed(future_to_mp4):
            returncode, mp4 = future.result()
            if returncode == 0:
                print(f"{count}/{len(mp4_files)} - {mp4} processed successfully.")
            else:
                print(f"{count} - {mp4} processing failed.")
            count += 1

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python convert_videos.py <input_directory>")
        sys.exit(1)
    
    input_directory = sys.argv[1]
    if not os.path.isdir(input_directory):
        print(f"Error: {input_directory} is not a valid directory.")
        sys.exit(1)
    
    main(input_directory)

    sys.exit(0)