
import { useState, useEffect } from "react";
import { MemoryRouter as Router, Routes, Route } from 'react-router-dom';
import './App.css';

import Multiselect from 'multiselect-react-dropdown';

import { Match, Move, Player, Result, Config, MainStatus } from "./types";
import { defaultConfig, defaultMainStatus, multiSelectStyle } from "./defaults";
import magic from "./magic";

window.electron.ipcRenderer.sendMessage('getMatches',[]);
window.electron.ipcRenderer.sendMessage('getConfig',[]);

function Main() {

  const [matches, setMatches] = useState<Match[]>([]);
  const [results, setResults] = useState<Result[]>([]);
  const [config, setConfig] = useState<Config>(defaultConfig);
  const [mainStatus, setMainStatus] = useState<MainStatus>(defaultMainStatus);

  useEffect(() => getData(setMatches,setConfig),[])

  const handleChange = (value: any, field: string) => {
    setConfig(prevState => ({ ...prevState, [field]: value }))
    const stringifiedConfig = JSON.stringify({ ...config, [field]: value })
    window.electron.ipcRenderer.sendMessage('setConfig',stringifiedConfig);
  };

  function resetConfig(){
    setConfig(defaultConfig)
    const stringifiedConfig = JSON.stringify(defaultConfig)
    window.electron.ipcRenderer.sendMessage('setConfig',stringifiedConfig);
  }
  
  const dataFormSubmit = (e: React.SyntheticEvent) => {
    e.preventDefault();
    const results = magic(matches, config)
    setResults(results)
  }

  function generateVideo(){
    const stringifiedData = JSON.stringify({ config, results })
    window.electron.ipcRenderer.sendMessage('generateVideo',stringifiedData);
  }

  window.electron.ipcRenderer.once('status', (status: MainStatus) => {
    // eslint-disable-next-line no-console
    console.log('Status:', status);
    setMainStatus(status)
  });

  type Players = { [key: string]: number };
  const players:Players = {};
  const moves:Move[] = [];
  if(matches.length){
    matches.forEach( match => {
      match.moves.forEach( move => {
        moves.push(move)
        if(players[move.player]){
          players[move.player]++
        } else {
          players[move.player] = 1
        }
      })
    })
  }
  
  const tmp: Player[] = []
  Object.keys(players).forEach( (key, index) => {
    tmp.push({
      name: `${key}`,
      dropdownName: `${key} - ${players[key]}`, 
      id: index, 
      numShots: players[key]
    })
  })
  const sortedPlayersForDropdown = tmp.sort((a,b) => b.numShots - a.numShots).slice(1)


  return (
    <div className="main">
      <div className="nav">
        <h1 className="title">Barkiver</h1>
      </div>
      { matches.length ?
        <div>
          <div className="prelim-data-section">
            <div className="section-title">Data: </div>
            <div className="data-row">Matches: {matches.length}</div>
            <div className="data-row">Players: {Object.keys(players).length}</div>
            <div className="data-row">Shots: {moves.length}</div>
          </div>
          <div className='divider'></div>
          <div className="primary-control-section">
            <div className="section-title">Data Controls: </div>
            <div className="data-control-row">
                <button onClick={resetConfig}>Clear</button>
              </div>
            <form className="data-control-wrapper"
              onSubmit={dataFormSubmit}  
            >
              <div className="data-control-row">
                <div className="label">Players</div>
                <div className="multi-select">
                  <Multiselect
                    options={sortedPlayersForDropdown} 
                    selectedValues={config.players} 
                    onSelect={(newList) => handleChange(newList,"players")} 
                    onRemove={(newList) => handleChange(newList,"players")} 
                    displayValue="dropdownName" 
                    style={multiSelectStyle}
                  />
                </div>
              </div>
              <div className="data-control-row">
                <div className="label">Num:</div>
                <input className="input"
                  value={config.num}
                  onChange={(e) => handleChange(e.target.value,"num")}
                />
              </div>
              <div className="data-control-row">
                <div className="label">Sort:</div>
                <input className="input"
                  value={config.sortParam}
                  onChange={(e) => handleChange(e.target.value,"sortParam")}
                />
              </div>
              <div className="data-control-row">
                <div className="label">Shuffle:</div>
                <input className="input" type="checkbox"
                  checked={config.shuffle}
                  onChange={(e) => handleChange(e.target.value,"shuffle")}
                />
              </div>
              <div className="data-control-row">
                <div className="label">Start Seconds:</div>
                <input className="input"
                  value={config.startSeconds}
                  onChange={(e) => handleChange(e.target.value,"startSeconds")}
                />
              </div>
              <div className="data-control-row">
                <div className="label">End Seconds:</div>
                <input className="input"
                  value={config.endSeconds}
                  onChange={(e) => handleChange(e.target.value,"endSeconds")}
                />
              </div>
              <div className="data-control-row">
                <div className="label">Custom:</div>
                <input className="input"
                  value={config.custom}
                  onChange={(e) => handleChange(e.target.value,"custom")}
                />
              </div>
              <div className="data-control-row">
                <button>Run</button>
              </div>
            </form>
          </div>
          <div className='divider'></div>
          <div className="results-section">
            <div className="section-title">Results: </div>
            <div>Total: {results.length}</div>
            {results.slice(0,10).map( (result,index) => {
              return (<div key={index}>
                <div>{result.match.videoLink}</div>
                <div>{`${result.start} - ${result.end}`}</div>
              </div>)
            })}
          </div>
          <div className='divider'></div>
          <div className="video-section">
            <div className="section-title">Video Controls: </div>
            <div>Total: {results.length}</div>
            <div className="data-control-row">
              <div className="label">Archive Path:</div>
              <input className="input"
                value={config.ytdlArchivePath}
                onChange={(e) => handleChange(e.target.value,"ytdlArchivePath")}
              />
            </div>
            <div className="data-control-row">
              <div className="label">outputPath:</div>
              <input className="input"
                value={config.outputPath}
                onChange={(e) => handleChange(e.target.value,"outputPath")}
              />
            </div>
            <div className="data-control-row">
              <div className="label">qualityMode:</div>
              <input className="input"
                value={config.qualityMode}
                onChange={(e) => handleChange(e.target.value,"qualityMode")}
              />
            </div>
            <div className="generationWrapper">
            { mainStatus.isBusy ?
              <div className="mainStatusMessage">{mainStatus.message}</div>
              :
              <button onClick={() => generateVideo()} className="bigGreenButton">GO</button>    
            }
            </div>
          </div>
        </div>
        : 
        <div className="loading">Loading...</div>
      }
    </div>
  );
}


export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Main />} />
      </Routes>
    </Router>
  );
}


function getData(setMatches: any, setConfig: any){
  // get data
  window.electron.ipcRenderer.once('matches', (matches: Array<Match>) => {
    // eslint-disable-next-line no-console
    console.log('Matches:', matches);
    setMatches(matches)
  });

  window.electron.ipcRenderer.once('config', (savedConfig: Config) => {
    // eslint-disable-next-line no-console
    console.log('Saved Config', savedConfig);
    setConfig(savedConfig)
  });

}