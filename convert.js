// ffmpeg -y -i f_current.mp4 -vf "setpts=1.25*PTS" -r 15 f_current_.mp4


const { lstatSync, readdirSync } = require("fs")
const { asyncForEach } = require("./lib")
const { spawn } = require("child_process")
const path = require("path")

const inputDir = "/home/matt/Projects/barkiver/output/output114"
const outputDir = "/home/matt/Projects/barkiver/output/output114/converted"

const inputFiles = readdirSync(inputDir)

console.log("Input Files: ", inputFiles.length )

const mp4s = inputFiles.filter(file => file.includes(".mp4"))

console.log("mp4 Files: ", mp4s.length )

let count =  0
// asyncForEach(mp4s, async mp4 => {
//     await new Promise((resolve) => {
//         console.log(`${count++} - ${mp4}`)
//         const outputFile = path.resolve(outputDir, mp4)
//         const args = [
//             "-y",
//             "-i",
//             `${path.resolve(inputDir, mp4)}`,
//             '-vf',
//             "setpts=1.25*PTS",
//             "-r",
//             15,
//             `${outputFile}`
//         ]
//         console.log(`ffmpeg ${args.join(" ")}`)

//         const process = spawn('ffmpeg', args)
//         process.on("exit", resolve)
//     })
// })

// ffmpeg -i video1.mp4 -video_track_timescale 90000 video1_fixed.mp4
asyncForEach(mp4s, async mp4 => {
    await new Promise((resolve) => {
        console.log(`${count++} - ${mp4}`)
        const outputFile = path.resolve(outputDir, mp4)
        const args = [
            "-i",
            `${path.resolve(inputDir, mp4)}`,
            '-video_track_timescale',
            "90000",
            `${outputFile}`
        ]
        console.log(`ffmpeg ${args.join(" ")}`)

        const process = spawn('ffmpeg', args)
        process.on("exit", resolve)
    })
})