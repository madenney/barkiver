import os
import random
import sys

def generate_file_list(directory):
    # Output file for ffmpeg concat
    output_file = os.path.join(directory, 'file.txt')

    # Get list of MP4 files
    mp4_files = [f for f in os.listdir(directory) if f.endswith('.avi')]

    # Randomize the order
    random.shuffle(mp4_files)

    # Write to files.txt in the required format
    with open(output_file, 'w') as f:
        for mp4_file in mp4_files:
            f.write(f"file '{os.path.join(directory, mp4_file)}'\n")

    print(f"List of MP4 files written to {output_file} in random order.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python generate_file_list.py <directory>")
        sys.exit(1)
    
    input_directory = sys.argv[1]
    if not os.path.isdir(input_directory):
        print(f"Error: {input_directory} is not a valid directory.")
        sys.exit(1)
    
    generate_file_list(input_directory)