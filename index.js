
const youtubedl = require('youtube-dl-exec')
const fs = require('fs')
const path = require('path')
const logger = require('progress-estimator')()
const { spawn } = require("child_process")

const { asyncForEach, pad, shuffleArray } = require("./lib")

const getInfo = (url, flags) => youtubedl(url, { dumpSingleJson: true, ...flags })
async function fromInfo(infoFile, flags){
    const promise = youtubedl.exec('', { loadInfoJson: infoFile, ...flags })
    return await logger(promise, `Obtaining video`)
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

console.log("Billiards Archiver\n")

const matches = require("./data.json")


const shots = []

matches.forEach(match => {
    match.moves.forEach( move => {
        shots.push({
            videoLink: match.videoLink,
            ...move
        })
    })
})


console.log("Total Shots: ", shots.length)

const shuffled = shuffleArray(shots)

const filteredShots = shuffled.filter(s => {
    //if(s.player != "Shane Van Boening") return false
    if(s.outcome != "break") return false
    return true
})

console.log("Filtered Shots: ", filteredShots.length )

 
const clips = []
filteredShots.slice(0,5).forEach(shot => {

    const tmp = shot.time.split(':')
    const seconds = (+tmp[0]) * 60 * 60 + (+tmp[1]) * 60 + (+tmp[2]); 

    let start = seconds - 1
    if(start == 0 ) start = 1

    clips.push({
        videoLink: shot.videoLink,
        start,
        end: seconds + 9
    })
})

generateVideo(clips)


async function generateVideo(clips){
    console.log("Clips: ", clips.length)

    const links = []
    clips.forEach(clip => {
        if(links.indexOf(clip.videoLink) == -1 ){
            links.push(clip.videoLink)
        }
    })


    // download videos
    console.log(`Downloading ${links.length} videos...`)
    await asyncForEach( links, async (link) => {
        let info
        try {
            info = await getInfo(link)
        } catch(err){
            console.log("Error getting info from ", link)
            console.log(err)
            return 
        }
        if(!info){
            console.log("Error with: ")
            console.log(link)
            return
        }
        fs.writeFileSync('videoInfo.json', JSON.stringify(info))
        console.log(info.fulltitle)
        if(!info.fulltitle){
            console.log("No title?")
            console.log(info)
        }
        const t = info.fulltitle.split(" ").join("_")
        const path = `./archive/${t}`
        await fromInfo('videoInfo.json', { 
            output: path,
            downloadArchive: `./archive/downloadArchive`
        })

        clips.forEach(clip => {
            if(clip.videoLink == link ){
                clip.videoPath = `${path}.webm`
            }
        })
    })

    // slice videos
    console.log("\nCutting clips...")
    let outputDirectoryName = "output";
    const outputPath = "./output"
    let count = 1;
    while(fs.existsSync(path.resolve(`${outputPath}/${outputDirectoryName}`))){
        outputDirectoryName = `output${count++}`
    }
    fs.mkdirSync(path.resolve(outputPath + "/" + outputDirectoryName))
    count = 0
    await asyncForEach(clips, async clip => {
        if(!clip.video) return 
        console.log(clip)
        await new Promise((resolve,reject) => {

            const args = [
                "-ss",
                clip.start.toString().toHHMMSS(),
                "-to",
                clip.end.toString().toHHMMSS(),
                "-i",
                clip.videoPath,
                "-c",
                "copy",
                path.resolve(`${outputPath}/${outputDirectoryName}/${pad(count++,3)}.mp4`)
            ]
            console.log(args)
            const options = {}
            const process = spawn("ffmpeg", args, options)
            process.on("exit", resolve)
        })
    })

}

