

const { program } = require('commander');
const youtubedl = require('youtube-dl-exec')
const fs = require('fs')
const path = require('path')
const { spawn } = require("child_process")
const logger = require('progress-estimator')()
const { asyncForEach, pad, shuffleArray } = require("./lib")
const { accurateSlice } = require("./accurateslice")


const archivePath = "./archive"


async function main() {
    console.log("----- Pool Clipper -----\n")

    checkForArchivePath()
    
    const args = argParse();

    const matches = require("./data.json")

    const shots = findShots(args, matches)

    const clipTemplates = createClipTemplates(args, shots)

    if(args.data == true){
        console.log("Clip Templates: ", clipTemplates.length)
        if(args.bar){
            console.log("BARs: ", clipTemplates.filter(c => c.outcome == "break").length)
        }
        return
    }


    await downloadVideos(clipTemplates, matches)

    const outputDir = createOutputDir()

    const logPath = path.resolve(outputDir, "log.txt")
    fs.appendFileSync(logPath, `Directory: ${outputDir}`)

    await generateClips(args, clipTemplates, outputDir, logPath)

    console.log("\nDone.")
}


function findShots(args, matches){

    let shots = []


    // skip bad links TODO: fix bad links
    badLinks = fs.readFileSync('./archive/badLinks').toString().split("\n");

    matches.forEach(match => {

        if(badLinks.indexOf(match.videoLink) > -1) return

        match.moves.forEach( move => {

            const shot = {
                videoTitle: match.videoTitle,
                videoLink: match.videoLink,
                videoPath: match.videoPath, // might be undefined
                eventType: match.eventType,
                eventName: match.eventName,
                ...move
            }

            shots.push(shot)
        })
    })

    console.log("Total Shots: ", shots.length)

    if(args.gameType){
        switch (args.gameType){
            case "8":
                shots = shots.filter(shot => shot.eventType == "8")
                break
            case "9":
                shots = shots.filter(shot => shot.eventType == "9")
                break
            case "10":
                shots = shots.filter(shot => shot.eventType == "10")
                break
            case "9+":
                shots = shots.filter(shot => (shot.eventType == "9" || shot.eventType == "10"))
                break
            default:
                throw new Error("Error: Invalid GameType:", args.gameType)
        }
    }

    if(args.bar){
        console.log("-- Break and Runs only")
        let bars = []
        let tmp = []
        let player = null
        shots.forEach(shot => {
            if(shot.outcome == "break"){
                if(tmp.length > 0){
                    bars.push(tmp)
                }
                player = shot.player
                tmp = [shot]
                return
            }
            if(tmp.length > 0 && shot.outcome == "made" && shot.player == player){
                tmp.push(shot)
            } else {
                tmp = []
            }
        })


        console.log("#BreakAndRuns: ", bars.length)
        shots = []
        bars.forEach(bar => {
            if(bar.length > 5 ){
                bar.forEach(shot => shots.push(shot))
            }
        })
    }

    if(args.player){
        shots = shots.filter(s => {
            if(s.player.toLowerCase() != args.player.toLowerCase()) return false
            return true
        })
    }


    console.log("Filtered Shots: ", shots.length )

    if(args.shuffle) shots = shuffleArray(shots)

    if(args.sort){
        shots = shots.sort((a,b) => {
            return parseFloat(b[param]) - parseFloat(a[param])
        })
    }

    if(args.verbose){
        shots.slice(0,args.clips).forEach( shot => console.log(shot))
    }

    return shots.slice(0, args.clips)

}

function createClipTemplates(args,shots){
    const clipTemplates = []

    shots.forEach((shot, index) => {

        const tmp = shot.time.split(':')
        const seconds = (+tmp[0]) * 60 * 60 + (+tmp[1]) * 60 + (+tmp[2]); 

        // let start = seconds 
        // if(start == 0 ) start = 1

        const newClipTemplate = {
            videoTitle: shot.videoTitle,
            videoLink: shot.videoLink,
            videoPath: shot.videoPath,
            eventName: shot.eventName,
            outcome: shot.outcome,
            player: shot.player,
            start: seconds,
            end: seconds + args.endSeconds        
        }

        if(shot.outcome == "break") newClipTemplate.end += args.breakEndSeconds
        // fix overlaps
        const lastClipTemplate = clipTemplates[clipTemplates.length-1]
        if(
            lastClipTemplate &&
            lastClipTemplate.outcome == "made" &&
            lastClipTemplate.player == newClipTemplate.player &&
            lastClipTemplate.end >= newClipTemplate.start - 1
        ) {
            lastClipTemplate.end = newClipTemplate.end
        } else {
            clipTemplates.push(newClipTemplate)
        }

    })

    return clipTemplates 
}


async function downloadVideos(clipTemplates, matches){

    const undownloadedLinks = []
    
    clipTemplates.forEach(clipTemplate => {
        if(!clipTemplate.videoPath){
            if(undownloadedLinks.indexOf(clipTemplate.videoLink) == -1){
                undownloadedLinks.push(clipTemplate.videoLink)
            }
        }
    })

    // download videos
    console.log(`\nDownloading ${undownloadedLinks.length} videos...\n`)
    //await asyncForEach( undownloadedLinks, async (link) => {
    let downloadCount = 1
    await asyncForEach( undownloadedLinks, async (link) => {

        console.log(`Video - ${downloadCount++}/${undownloadedLinks.length}`)
        console.log("Link: ", link)

        let videoPath = null

        try {
            await new Promise((resolve) => {
                const dlProcess = spawn('yt-dlp', [link, '-P', './archive/', '--restrict-filenames', '--no-playlist'])//--replace-in-metadata', "title,uploader", "[ ]", "_"])
                dlProcess.on("exit", resolve)
                dlProcess.stdout.on('data', (data) => {
                    const output = data.toString()

                    const downloadUpdateTag = '[download]'
                    if(output.indexOf(downloadUpdateTag) > -1 && output.indexOf("%") > -1 ){
                        process.stdout.clearLine()
                        process.stdout.cursorTo(0)
                        process.stdout.write(`${output.slice(downloadUpdateTag.length +2)}`)
                    }

                    if(output.indexOf("[Merger]") > -1){
                        // get everything between quotes
                        videoPath = path.resolve(output.split('"')[1])
                        console.log("\nDone: ", videoPath)
                    }

                    if(output.indexOf("already been downloaded") > -1){
                        // get everything between quotes
                        videoPath = path.resolve(output.slice(output.indexOf("]")+2, output.indexOf('.mkv') + 4))
                        //console.log("\nAlready downloaded:", videoPath)
                    }

                });
                dlProcess.stderr.on('data', (data) => {
                    console.error(`stderr: ${data}`);
                });
                
            })
        } catch(e){
            console.log("Error downloading")
            console.log(e)
            //fs.appendFileSync('./archive/badLinks', `\n${link}`);
            console.log("-------------------------------------------------------------")
            return
        }

        if(!videoPath){
            console.log("Error: No video path")
            console.log("-------------------------------------------------------------")
            return
        }

        clipTemplates.forEach(clip => {
            if(clip.videoLink == link ){
                clip.videoPath = videoPath
            }
        })

        // save videoPath
        const match = matches.find(match => match.videoLink == link )
        match.videoPath = videoPath
        fs.writeFileSync('./data.json', JSON.stringify(matches))
        
        console.log("-------------------------------------------------------------")

    })
    console.log("Done downloading.")
}


async function generateClips(args, clipTemplates, outputDir, logPath){
    console.log(`\nCutting ${clipTemplates.filter(c => c.videoTitle != "N/A - bad link").length} clips...\n`)

    count = 0
    await asyncForEach(clipTemplates, async clipTemplate => {
        process.stdout.clearLine()
        process.stdout.cursorTo(0)
        process.stdout.write(`${count}/${clipTemplates.length}`)
        if(clipTemplate.videoTitle == "N/A - bad link") return false
        const fileNumber = pad(count++,4).toString()
        await accurateSlice(
            clipTemplate.videoPath,
            fileNumber,
            outputDir,
            clipTemplate.start,
            clipTemplate.end,
            logPath
        )

        await addOverlay(args, clipTemplate, outputDir, fileNumber, logPath)
        try {
            fs.rmSync(path.resolve(outputDir,`${fileNumber}-sliced.mp4`))
        } catch(e){
            
        }
        fs.appendFileSync(logPath, `-------------------------------------------------------------------------------------\n`)

    })
}

async function addOverlay(args, clipTemplate, outputDir, fileNumber, logPath){

    const inputPath = path.resolve(outputDir, `${fileNumber}-sliced.mp4`)
    const outputPath = path.resolve(outputDir, `${fileNumber}.mp4`)

    const command = [
        '../video_tools/overlay.py', 
        inputPath, 
        outputPath,
        `Source: ${clipTemplate.eventName}`,
    ]

    if(args.addPlayerOverlay && clipTemplate.player) command.push(`Player: ${clipTemplate.player}` )
    
    fs.appendFileSync(logPath, `python3 ${command.join(" ")}\n`)

    await new Promise((resolve) => {
        const process = spawn('python3', command)
        process.on("exit", resolve)
        // process.stderr.on('data', (data) => {
        //     console.error(`overlay.py stderr: ${data}`);
        //     throw new Error("Error to escape process")
        // });
    })
}

function checkForArchivePath(){
    if(!fs.existsSync( archivePath )){
        console.log(`Archive path does not exist: ${archivePath}`)
        process.exit()
    }
    if(!fs.existsSync( path.resolve(archivePath, 'downloadArchive') )){
        fs.writeFileSync(path.resolve(archivePath, 'downloadArchive'), '')
    }
    if(!fs.existsSync( path.resolve(archivePath, 'badLinks') )){
        fs.writeFileSync(path.resolve(archivePath, 'badLinks'),'')
    }
}

function createOutputDir(){
    let outputDirectoryName = "output";
    const outputPath = "./output"
    let count = 1;
    while(fs.existsSync(path.resolve(`${outputPath}/${outputDirectoryName}`))){
        outputDirectoryName = `output${count++}`
    }
    const finalPath = path.resolve(outputPath + "/" + outputDirectoryName)
    fs.mkdirSync(finalPath)
    return finalPath
}

function argParse() {

    const validGameTypes = ["8", "9", "9+","10"]

    program
    .description('A tool for creating pool clips')
    .option('-c, --clips <number>', 'An integer count', 1)
    .option('-p, --player <string>', 'A name', '')
    .option('-e, --endSeconds <number>', 'An integer count', parseInt, 10)
    .option('-eb, --breakEndSeconds <number>', 'An integer count', parseInt, 0)
    .option('-bar, --bar', 'Only break and runs', false)
    .option('-data, --data', 'Only show data', false)
    .option('-po, --addPlayerOverlay', 'Add player overlay', false)
    .option('-g, --gameType <string>', 'Game Type', (value) => {
        if (!validGameTypes.includes(value.toString())) {
            console.log(`Invalid -g parameter: ${value}. Valid options are: ${validGameTypes.join(', ')}`)
            process.exit()
        }
        return value;
    })
    .addHelpText('after')
    .parse(process.argv)

    const args = program.opts();

    return args
}

main();
