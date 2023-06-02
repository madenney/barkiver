
import { useState, useEffect } from "react";
import { MemoryRouter as Router, Routes, Route } from 'react-router-dom';
import './App.css';

import Multiselect from 'multiselect-react-dropdown';
import { multiSelectStyle } from './rendererConfig';

import { Match, Move, Player, Result, Config } from "./types";
import { defaultConfig } from "./defaultConfig";


window.electron.ipcRenderer.sendMessage('getMatches',[]);
window.electron.ipcRenderer.sendMessage('getConfig',[]);

function Main() {

  const [matches, setMatches] = useState<Match[]>([]);
  const [results, setResults] = useState<Result[]>([]);
  const [config, setConfig] = useState<Config>(defaultConfig);

  useEffect(() => getData(setMatches,setConfig),[])


  const handleChange = (value: any, field: string) => {
    setConfig(prevState => ({ ...prevState, [field]: value }))
    const stringifiedConfig = JSON.stringify({ ...config, [field]: value })
    window.electron.ipcRenderer.sendMessage('setConfig',stringifiedConfig);
  };

  

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
    tmp.push({name: `${key} - ${players[key]}`, id: index, numShots: players[key]})
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
            <div className="data-control-wrapper">
              <div className="data-control-row">
                <div className="label">Players</div>
                <div className="multi-select">
                  <Multiselect
                    options={sortedPlayersForDropdown} 
                    selectedValues={config.players} 
                    onSelect={(newList) => handleChange(newList,"players")} 
                    onRemove={(newList) => handleChange(newList,"players")} 
                    displayValue="name" 
                    style={multiSelectStyle}
                  />
                </div>
              </div>
              <div className="data-control-row">
                <div className="label">Param:</div>
                <input className="input">Param:</input>
              </div>
              <div className="data-control-row"></div>
              <div className="data-control-row"></div>
              <div className="data-control-row"></div>
              <div className="data-control-row"></div>
              <div className="data-control-row"></div>
            </div>

          </div>
          <div className='divider'></div>
          <div className="results-section">
            <div className="section-title">Results: </div>
            <div>Total: {results.length}</div>
          </div>
          <div className='divider'></div>
          <div className="video-section">
            <div className="section-title">Video Controls: </div>
            <div>Total: {results.length}</div>
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