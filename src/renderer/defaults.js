
export const defaultConfig = {
    num: 0,
    slice: 0,
    shuffle: false,
    sortParam: "",
    players: [],
    custom: "",
    startSeconds: 2,
    endSeconds: 8,
    HQMode: false,
    removeOverlap: true,
    ytdlArchivePath: "",
    outputPath: "",
    qualityMode: "",
  }
  
export const defaultMainStatus = {
  isBusy: false,
  message: ""
}

// multiselect docs:
// https://www.npmjs.com/package/multiselect-react-dropdown
export const multiSelectStyle = {
  "multiSelectContainer": { "display":"inlineBlock"},
  "searchBox": {
      "width": "300px",
      "backgroundColor": "#101010", 
      "height": "40px", 
      "maxHeight": "40px", 
      "overflowY": "scroll"
  }, 
  "option": {
      "backgroundColor": "#101010", 
      "fontSize": "15px"
  }, 
  "optionContainer": { "display":"inlineBlock"},
  "chips": {"backgroundColor": "#101010"}
} 