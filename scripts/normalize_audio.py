import os
import sys
from subprocess import run

def normalize_audio(input_file):
    # Get the absolute path of the input file
    input_path = os.path.abspath(input_file)
    
    # Get the directory of the input file
    input_dir = os.path.dirname(input_path)
    
    # Create the output file path
    output_file = os.path.join(input_dir, 'final_audio_normalized.avi')
    
    # Run the FFmpeg command
    ffmpeg_command = [
        'ffmpeg', '-i', input_path,
        '-af', 'loudnorm=I=-23:LRA=7:TP=-2,compand=gain=-6',
        '-c:v', 'copy', output_file
    ]
    run(ffmpeg_command)
    print(f'Output file created at: {output_file}')

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py <input_file>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    normalize_audio(input_file)