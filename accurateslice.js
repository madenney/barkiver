


const { spawn } = require("child_process")
const fs = require('fs')
const path = require('path')


// Takes .webm, cuts around it, converts it to mp4 with high density keyframes, then cuts an accurate slice
module.exports.accurateSlice = async function(input, outputName, outputDir, start, end){
    console.log("Video Path: ", input)
    try {
    const output = path.resolve(outputDir,outputName)
    const inputPath = path.resolve(input)
    const keyFramesPath = path.resolve(outputDir,"keyframes.txt")
    const logPath = path.resolve(outputDir,"log.txt")
    
    // write keyframes to file
    await new Promise((resolve) => {
        const process = spawn('./getKeyFrames.sh', [`${inputPath}`, keyFramesPath])
        process.on("exit", resolve)
    })

    // get nearest key frames
    const keyFrames = fs.readFileSync(keyFramesPath).toString().split("\n");
    let nearestStartKeyFrame = 0
    for(let i = 0; i < keyFrames.length;i++){
        if(keyFrames[i] < start ){
            nearestStartKeyFrame = keyFrames[i]
        } else {
            break
        }
    }
    let nearestEndKeyFrame = keyFrames[keyFrames.length -2]
    for(let i = keyFrames.length -2; i > 0; i--){
        if(keyFrames[i] > end ){
            nearestEndKeyFrame = keyFrames[i]
        } else {
            break
        }
    }
    console.log("Nearest Start Keyframe: ", nearestStartKeyFrame)
    console.log("Nearest End Keyframe: ", nearestEndKeyFrame)

    // cut around clip at nearest keyframes
    const lrgSliceArgs = [`-ss`,`${nearestStartKeyFrame}`,`-to`,`${nearestEndKeyFrame}`,`-i`,`${inputPath}`,`-c`,`copy`,`${output}-lrg.webm`]
    fs.appendFileSync(logPath, `ffmpeg ${lrgSliceArgs.join(" ")}\n\n`)
    await new Promise((resolve) => {
        const process = spawn('ffmpeg', lrgSliceArgs)
        process.on("exit", resolve)
    })

    // convert to high density mp4
    const conversionArgs = [`-i`,`${output}-lrg.webm`,`-c:v`,`libx264`,`-x264opts`,`keyint=1`,`${output}-lrg.mp4`]
    fs.appendFileSync(logPath, `ffmpeg ${conversionArgs.join(" ")}\n\n`)
    await new Promise((resolve) => {
        const process = spawn('ffmpeg', conversionArgs)
        process.on("exit", resolve)
    })
    
    // accurately cut
    const startDiff = start - nearestStartKeyFrame
    const accurateSliceArgs = [`-ss`,`${startDiff}`,`-to`,`${startDiff+(end-start)}`,`-i`,`${output}-lrg.mp4`,`${output}.mp4`]
    fs.appendFileSync(logPath, `ffmpeg ${accurateSliceArgs.join(" ")}\n`)
    await new Promise((resolve) => {
        const process = spawn('ffmpeg', accurateSliceArgs)
        process.on("exit", resolve)
    })
 
    // delete files
    fs.rmSync(`${output}-lrg.webm`)
    fs.rmSync(`${output}-lrg.mp4`)
    
    fs.appendFileSync(logPath, `-------------------------------------------------------------------------------------\n`)

    }catch(err){
        return false
    }
}

String.prototype.toHHMMSS = function () {
    var sec_num = parseInt(this, 10);
    var hours   = Math.floor(sec_num / 3600);
    var minutes = Math.floor((sec_num - (hours * 3600)) / 60);
    var seconds = sec_num - (hours * 3600) - (minutes * 60);

    if (hours   < 10) {hours   = "0"+hours;}
    if (minutes < 10) {minutes = "0"+minutes;}
    if (seconds < 10) {seconds = "0"+seconds;}
    return hours+':'+minutes+':'+seconds;
}