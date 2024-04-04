
import fs from "fs"
import path from "path"
const youtubedl = require('youtube-dl-exec')
const logger = require('progress-estimator')()

import { Config, Result, Match } from "../renderer/types"
import { asyncForEach } from "../../lib"

export default async function generateVideo(event: Electron.IpcMainEvent, config: Config, results: Result[]){

    console.log("RESULTS: ", results.length)
    event.reply("status", {
        isBusy: true,
        message: "Generating Video..."
    })

    const undownloadedLinks: string[] = []
    const undownloadedMatches: Match[] = []
    results.forEach(result => {
        if(!fs.existsSync(result.match.videoPath)){
            if(undownloadedLinks.indexOf(result.match.videoLink) == -1 ){
                undownloadedLinks.push(result.match.videoLink)
            }
            undownloadedMatches.push(result.match)
        }
    })
    console.log("undownloadedLinks: ", undownloadedLinks.length)
    console.log("undownloadedMatches: ", undownloadedMatches.length)

    await asyncForEach( undownloadedLinks, async (link: string) => {

        console.log(link)
        let info
        try {
            const tmp = link.split("&list")[0]
            console.log("TMP: ", tmp)
            info = await getInfo(tmp,{})
            if(!info) throw "info undefined"
        } catch(err){
            console.log("Error getting info: ")
            console.log(err)
            fs.appendFileSync(path.resolve(config.outputPath, "error.txt"), `\n${link}`);
            console.log("-------------------------------------------------------------")
            return 
        }

        fs.writeFileSync(path.resolve(config.ytdlArchivePath,'videoInfo.json'), JSON.stringify(info))
        if(!info.title){
            console.log("No title?")
            console.log("video id: ", info.id)
            console.log("-------------------------------------------------------------")
            return 
        }

        console.log(info.title)

        const t = info.title.split(" ").join("_")
        await fromInfo(path.resolve(config.ytdlArchivePath,'videoInfo.json'), { 
            output: path.resolve(config.ytdlArchivePath, t),
            downloadArchive: path.resolve(config.ytdlArchivePath, 'downloadArchive')
        })

        console.log("-------------------------------------------------------------")
    })
    console.log("Done downloading.")

    event.reply("status", {
        isBusy: false,
        message: "Done :)"
    })
}

async function getInfo(url: string, flags:{}){ 
    return await youtubedl(url, { dumpSingleJson: true, ...flags })
}

async function fromInfo(infoFile: string, flags: {}){
    const promise = youtubedl.exec('', { loadInfoJson: infoFile, ...flags })
    return await logger(promise, `Downloading`)
}