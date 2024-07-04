import os

def pad_filenames(directory):
    # Get all filenames in the directory
    filenames = os.listdir(directory)
    print(filenames)
    # Determine the maximum length of filenames
    max_length = max(len(name) for name in filenames)
    print(max_length)

    # Pad each filename with zeros at the beginning to make them the same length
    for filename in filenames:
        new_filename = filename.zfill(max_length)
        # Renaming the file
        os.rename(os.path.join(directory, filename), os.path.join(directory, new_filename))
        print(f"Renamed '{filename}' to '{new_filename}'")

# Usage: Use the current working directory
directory_path = os.getcwd()
pad_filenames(directory_path)