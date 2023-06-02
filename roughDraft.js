
const youtubedl = require('youtube-dl-exec')
const fs = require('fs')
const path = require('path')
const logger = require('progress-estimator')()
const { spawn } = require("child_process")
const { asyncForEach, pad, shuffleArray } = require("./lib")
const { accurateSlice } = require("./accurateslice")


const startingNumber = 9999
const startSeconds = 2
const endSeconds = 8
const shuffle = true
const sort = false
const param = "pocketDist"
const HQmode = true
const player = false
// const player = "Joshua Filler"
//const players = ["Francisco Sanchez Ruiz"]
const players = ["Shane Van Boening", "Joshua Filler", "Francisco Sanchez Ruiz", "Fedor Gorst", "Dennis Orcollo"]
// const player = null
const printNShots = 0
const onlyPrint = false

main()
async function main(){
    console.log("----- Billiards Archiver -----\n")
    const matches = require("./data.json")
    // await fixData(matches)
    const clips = await generateClips(matches)
    //const clips = await breakAndRuns(matches)
    if(onlyPrint) return false
    await generateVideo(clips)
    console.log("Done :)")
}

function analyze(clips){
    let last = ""
    clips.forEach(clip => {
        if(clip.videoTitle == last)return
        last = clip.videoTitle
        console.log(clip.videoTitle)
        console.log(clip.videoLink)
    })
}

async function breakAndRuns(matches){

    const bars = []

    matches.forEach( match => {
        let tmp = []
        const str = `${match.videoTitle.split(" ").join("_")}.webm`
        console.log(str)
        if(!str.includes("2021_World_Pool_Championship_|_Table_Two")){
            return false
        }

        match.moves.forEach(move => {
            if(players.indexOf(move.player) == -1){
                tmp = []
                return false
            }

            if(move.outcome == "break"){
                if(tmp.length > 0 ){
                    const bar = []
                    tmp.forEach(m => bar.push(m))
                    bars.push(bar)
                }
                tmp = [{
                    videoTitle: match.videoTitle,
                    videoLink: match.videoLink,
                    player1: match.player1,
                    player2: match.player2,
                    ...move
                }]
            } else if (move.outcome == "made" ){
                console.log(tmp.length)
                if(tmp[0] && tmp[0].outcome == "break"){
                    tmp.push({
                        videoTitle: match.videoTitle,
                        videoLink: match.videoLink,
                        ...move
                    })
                } else {
                    tmp = []
                }
            } else {
                tmp = []
            }
        })
    })

    const clips = []

    // speedrun mode
    bars.slice(0,startingNumber).forEach(bar => {
        bar.forEach( shot => {
            const tmp = shot.time.split(':')
            const seconds = (+tmp[0]) * 60 * 60 + (+tmp[1]) * 60 + (+tmp[2]); 
    
            let start = seconds - startSeconds
            let end = seconds + endSeconds
            
            clips.push({
                videoTitle: shot.videoTitle,
                videoLink: shot.videoLink,
                start,
                end  
            })
        })
    })

    // normal mode
    // bars.slice(0,startingNumber).forEach(bar => {
    //     bar.forEach( shot => {
    //         const tmp = shot.time.split(':')
    //         const seconds = (+tmp[0]) * 60 * 60 + (+tmp[1]) * 60 + (+tmp[2]); 
    
    //         let start = seconds - startSeconds
    //         if(start == 0 ) start = 1
    
    //         if(
    //             clips.length > 0 && 
    //             clips[clips.length-1].end + 4 > start &&
    //             bar.indexOf(shot) > 0
    //         ){
    //             clips[clips.length-1].end = seconds + endSeconds
    //         } else {
    //             let _s = endSeconds
    //             if(shot.outcome == "break"){
    //                 _s = _s + 1 
    //             } else {
    //                 _s = _s 
    //             }
    //             clips.push({
    //                 videoTitle: shot.videoTitle,
    //                 videoLink: shot.videoLink,
    //                 start,
    //                 end: seconds + _s     
    //             })
    //         }
    //     })
    // })
    if(printNShots){
        clips.slice(0,printNShots).forEach( shot => console.log(shot))
    }
    return clips
}

async function generateClips(matches){

    let shots = []

    matches.forEach(match => {
        match.moves.forEach( move => {
            shots.push({
                videoTitle: match.videoTitle,
                videoLink: match.videoLink,
                ...move
            })
        })
    })

    console.log("Total Shots: ", shots.length)
    shots = shots.filter(s => {
        const str = `${s.videoTitle.split(" ").join("_")}.webm`
        if(!str.includes("2021_World_Pool_Championship_|_Table_Two")) return false
        if(player && s.player != player) return false
        if( !s[param] || s[param] == "-") return false
        s[param] = s[param].split(" ")[0]
        if(s.outcome != "made") return false
        return true
    })

    console.log("Filtered Shots: ", shots.length )

    if(shuffle) shots = shuffleArray(shots)

    if(sort){
        shots = shots.sort((a,b) => {
            return parseFloat(b[param]) - parseFloat(a[param])
        })
    }

    if(printNShots){
        shots.slice(0,printNShots).forEach( shot => console.log(shot))
    }

    
    const clips = []

    shots.slice(0,startingNumber).forEach(shot => {

        const tmp = shot.time.split(':')
        const seconds = (+tmp[0]) * 60 * 60 + (+tmp[1]) * 60 + (+tmp[2]); 

        let start = seconds 
        if(start == 0 ) start = 1

        // UI goes here
        clips.push({
            videoTitle: shot.videoTitle,
            videoLink: shot.videoLink,
            start,
            end: seconds + endSeconds        
        })
    })

    return clips 
}


async function generateVideo(clips){
    console.log("Clips: ", clips.length)

    const clipLinks = []
    clips.forEach(clip => {
        if(clipLinks.indexOf(clip.videoLink) == -1 ){
            clipLinks.push(clip.videoLink)
        }
    })
    console.log("Videos: ", clipLinks.length)

    // already downloaded ids
    let lines = fs.readFileSync('./archive/downloadArchive').toString().split("\n");
    const ids = []
    lines.forEach(line => {
        ids.push(line.split(" ")[1])
    })

    // bad links
    lines = fs.readFileSync('./archive/badLinks').toString().split("\n");
    const badLinks = []
    lines.forEach(line => {
        badLinks.push(line)
    })

    const undownloadedLinks = []
    clipLinks.forEach(link => {

        if(badLinks.indexOf(link) > -1 ) return false

        let videoId = "tmp"
        let tmp = link.split("?v=")
        if(!tmp[1]){
            videoId = tmp[0].split("youtu.be/")[1].split("&")[0]
        } else {
            videoId = tmp[1].split("&")[0]
        }
        
        if(ids.indexOf(videoId) == -1 ){
            undownloadedLinks.push(link)
        }
    })

    // download videos
    console.log(`\nDownloading ${undownloadedLinks.length} videos...`)
    await asyncForEach( undownloadedLinks, async (link) => {

        console.log(link)
        let info
        try {
            const tmp = link.split("&list")[0]
            info = await getInfo(tmp)
            if(!info) throw "info undefined"
        } catch(err){
            console.log("Error getting info: ")
            console.log(err)
            fs.appendFileSync('./archive/badLinks', `\n${link}`);
            console.log("-------------------------------------------------------------")
            return 
        }

        fs.writeFileSync('videoInfo.json', JSON.stringify(info))
        if(!info.title){
            console.log("No title?")
            console.log("video id: ", info.id)
            console.log("-------------------------------------------------------------")
            return 
        }

        console.log(info.title)

        const t = info.title.split(" ").join("_")
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

        console.log("-------------------------------------------------------------")
    })
    console.log("Done downloading.")


    //asdfasdf
    clips.forEach(clip => {
        if(clip.videoTitle == "N/A - bad link") return false
        if(!clip.videoPath){
            clip.videoPath = `./archive/${clip.videoTitle.split(" ").join("_")}.webm`
        }
    })


    

    console.log(`\nCutting ${clips.filter(c => c.videoTitle != "N/A - bad link").length} clips...\n`)

    // make output directory videos
    let outputDirectoryName = "output";
    const outputPath = "./output"
    let count = 1;
    while(fs.existsSync(path.resolve(`${outputPath}/${outputDirectoryName}`))){
        outputDirectoryName = `output${count++}`
    }
    fs.mkdirSync(path.resolve(outputPath + "/" + outputDirectoryName))

    if(HQmode){
         // Accurate Slice:
        count = 0
        await asyncForEach(clips, async clip => {
            process.stdout.clearLine()
            process.stdout.cursorTo(0)
            process.stdout.write(`${count}/${clips.length}`)
            if(clip.videoTitle == "N/A - bad link") return false
            await accurateSlice(
                clip.videoPath,
                pad(count++,3).toString(),
                path.resolve(`${outputPath}/${outputDirectoryName}`),
                clip.start,
                clip.end
            )
        })
    } else {

        count = 0
        const ffmpegLogPath = path.resolve(outputPath + "/" + outputDirectoryName + "/" + "log.txt")
        await asyncForEach(clips, async clip => {
            if(clip.videoTitle == "N/A - bad link") return false
            process.stdout.clearLine()
            process.stdout.cursorTo(0)
            process.stdout.write(`${count}/${clips.length}`)
            if(!clip.videoPath) {
                if(!clip.videoTitle){
                    console.log("No videoTitle?")
                    return
                }
                const t = clip.videoTitle.split(" ").join("_")
                const videoPath = `./archive/${t}`
                clip.videoPath = `${videoPath}.webm`
            } 

            const args = [
                "-ss",
                clip.start.toString().toHHMMSS(),
                "-to",
                clip.end.toString().toHHMMSS(),
                "-i",
                clip.videoPath,
                "-crf",
                "1",
                "-c",
                "copy",
                "-fflags",
                "+genpts",
                path.resolve(`${outputPath}/${outputDirectoryName}/${pad(count++,3)}.webm`)
            ]
            fs.appendFileSync(ffmpegLogPath, `${count-1}\n`)
            fs.appendFileSync(ffmpegLogPath, `${clip.start} - ${clip.end}\n`)
            fs.appendFileSync(ffmpegLogPath, `${clip.videoTitle}\n${clip.videoLink}\nffmpeg ${args.join(" ")}\n\ \n`)
            await new Promise((resolve,reject) => {
                //console.log(`ffmpeg ${args.join(" ")}`)
                const process = spawn("ffmpeg", args)
                process.on("exit", () => {
                    //console.log("\n--------------------------------------------------------------------------")
                    resolve()
                })
            })
        })
    }
    process.stdout.clearLine()
    process.stdout.cursorTo(0)
    process.stdout.write(`${count}/${clips.length}\n`)
}


async function getInfo(url, flags){ 
    return await youtubedl(url, { dumpSingleJson: true, ...flags })
}

async function fromInfo(infoFile, flags){
    const promise = youtubedl.exec('', { loadInfoJson: infoFile, ...flags })
    return await logger(promise, `Downloading`)
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


async function fixData(matches){

    let shots = []
    matches.forEach(match => {
        match.moves.forEach( move => {
            shots.push({
                videoTitle: match.videoTitle,
                videoLink: match.videoLink,
                ...move
            })
        })
    })

    shots = shots.filter(s => s.player == player)

    const uniqueLinksAndTitles = []
    shots.forEach(s => {
        if(!uniqueLinksAndTitles.find(l => l.videoLink == s.videoLink)){
            uniqueLinksAndTitles.push(s)
        }
    })

    await asyncForEach(uniqueLinksAndTitles, async u => {
        const p = `./archive/${u.videoTitle.split(" ").join("_")}.webm`
        if(!fs.existsSync(p)){
            console.log(p)
            console.log(u.videoLink)

            let info
            try {
                const tmp = u.videoLink.split("&list")[0]
                console.log(tmp)
                info = await getInfo(tmp)
                if(!info) throw "info undefined"
            } catch(err){
                console.log("Error getting info: ")
                //fs.appendFileSync('./archive/badLinks', `\n${match.videoLink}`);
                //match.videoTitle = "N/A - bad link"
                //fs.writeFileSync('./data.json', JSON.stringify(matches))
                console.log("-------------------------------------------------------------")
                return 
            }
            console.log("DONWLOADING: ")
            await fromInfo('videoInfo.json', { 
                output: path,
                downloadArchive: `./archive/downloadArchive`
            })
            console.log("-------------------------------------------------------------")
        }
    }) 

}


// Used to add Video Names to data.json
async function addVideoName(matches){
    let count = 0
    asyncForEach(matches, async match => {

        
        count++
        console.log(`${count}/${matches.length}`)
        console.log(match.videoLink)
        if(match.videoTitle){
            console.log('already done')
            return
        }
        let info
        try {
            const tmp = match.videoLink.split("&list")[0]
            info = await getInfo(tmp)
            if(!info) throw "info undefined"
        } catch(err){
            console.log("Error getting info: ")
            console.log(err)
            fs.appendFileSync('./archive/badLinks', `\n${match.videoLink}`);
            match.videoTitle = "N/A - bad link"
            fs.writeFileSync('./data.json', JSON.stringify(matches))
            console.log("-------------------------------------------------------------")
            return 
        }
        console.log(info.title)
        match.videoTitle = info.title
        console.log("writing...")
        fs.writeFileSync('./data.json', JSON.stringify(matches))
        console.log("-------------------------------------------------------------")
    })
    return 
}
