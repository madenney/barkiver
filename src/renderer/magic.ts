
import { Match, Move, Player, Result, Config } from "./types";


export default function magic(matches: Match[], config: Config){

    let results: Result[] = []
    let _matches: Match[] = matches
    if( config.players ){
        _matches = matches.filter(match => {
            return match.moves.find( move => {
                return config.players.map(p=>p.name).indexOf(move.player) > -1
            })
        })
    }
    console.log(_matches.length)
    if( config.custom === "bars"){
        results =  breakAndRuns(_matches, config)
    }

    return results;
}



const breakAndRuns = function (matches: Match[], config: Config){
    console.log("Bars man, bars")
    const results: Result[] = []

    matches.forEach( match => {
        let tmp: Move[] = []
        const bars: Move[][] = []

        match.moves.forEach(move => {
            if(config.players.map(p=>p.name).indexOf(move.player) == -1){
                tmp = []
                return false
            }

            if(move.outcome == "break"){
                if(tmp.length > 0 ){
                    const bar: Move[] = []
                    tmp.forEach(m => bar.push(m))
                    bars.push(bar)
                }
                tmp = [{
                    videoLink: match.videoLink,
                    ...move
                }]
            } else if (move.outcome == "made" ){
                if(tmp[0] && tmp[0].outcome == "break"){
                    tmp.push({
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
        
        bars.forEach(bar => {
            bar.forEach( shot => {
                const tmp = shot.time.split(':')
                const seconds = (+tmp[0]) * 60 * 60 + (+tmp[1]) * 60 + (+tmp[2]); 
        
                let start = seconds - config.startSeconds
                if(start == 0 ) start = 1
        
                if(
                    results.length > 0 && 
                    results[results.length-1].end + 4 > start &&
                    bar.indexOf(shot) > 0
                ){
                    results[results.length-1].end = seconds + config.endSeconds
                } else {
                    let _s = config.endSeconds
                    results.push({
                        match,
                        start,
                        end: seconds + _s     
                    })
                }
            })
        })
    })
    
    return results

}