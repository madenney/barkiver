
const { readdirSync, mkdirSync } = require("fs");
const { spawn } = require("child_process");
const path = require("path");

const inputDir = process.argv[2];
if (!inputDir) {
    console.error("Usage: node script.js <input_directory>");
    process.exit(1);
}

const outputDir = path.resolve(inputDir, "converted");
mkdirSync(outputDir, { recursive: true });

const inputFiles = readdirSync(inputDir);
const mp4s = inputFiles.filter(file => file.includes(".mp4"));

console.log("mp4 Files: ", mp4s.length);

let count = 0;

const asyncForEach = async (array, callback) => {
    for (let index = 0; index < array.length; index++) {
        await callback(array[index], index, array);
    }
};

asyncForEach(mp4s, async mp4 => {
    await new Promise((resolve) => {
        console.log(`${count++} - ${mp4}`);
        const outputFile = path.resolve(outputDir, mp4);
        const args = [
            "-i", path.resolve(inputDir, mp4),
            "-video_track_timescale", "90000",
            outputFile
        ];
        console.log(`ffmpeg ${args.join(" ")}`);

        const process = spawn('ffmpeg', args);
        process.on("exit", resolve);
    });
});