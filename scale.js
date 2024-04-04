


const { lstatSync, readdirSync } = require("fs")
const { asyncForEach } = require("./lib")
const { spawn } = require("child_process")
const path = require("path")

const inputDir = "/home/matt/Projects/barkiver/output/output53"
const outputDir = "/home/matt/Projects/barkiver/output/scale_output"

const inputFiles = readdirSync(inputDir)

console.log("Input Files: ", inputFiles.length )

const mp4s = inputFiles.filter(file => file.includes(".mp4"))

console.log("mp4 Files: ", mp4s.length )

let count =  0
asyncForEach(mp4s, async mp4 => {
    await new Promise((resolve) => {
        console.log(`${count++} - ${mp4}`)
        const outputFile = path.resolve(outputDir, mp4)
        const args = [
            "-i",
            `${path.resolve(inputDir, mp4)}`,
            '-vf',
            'scale=1920:1080',
            `${outputFile}`
        ]
        console.log(`ffmpeg ${args.join(" ")}`)

        const process = spawn('ffmpeg', args)
        process.on("exit", resolve)
    })
})