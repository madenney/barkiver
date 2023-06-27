
export type Match = {
  id: number;
  player1:  string;
  player2: string;
  matchLink:  string;
  videoLink:  string;
  videoPath:  string;
  eventName:  string;
  eventType: string;
  eventLink:  string;
  moves: [Move]
}

export type Move = {
  index:  string;
  player:  string;
  outcome:  string;
  time:  string;
  strength:  string;
  distance:  string;
  pocketDist:  string;
  posDist:  string;
  english:  string;
  cut:  string;
  complexity: string;
  videoLink?: string;
}

export type Player = {
  dropdownName: string;
  name: string;
  id: number;
  numShots: number;
}

export type Result = {
  start: number;
  end: number;
  match: Match
}

export type Config = {
  num: number;
  slice: number;
  shuffle: boolean;
  sortParam: string;
  players: Array<Player>;
  custom: string;
  startSeconds: number;
  endSeconds: number;
  HQMode: boolean;
  removeOverlap: boolean;

  ytdlArchivePath: string;
  outputPath: string;
  qualityMode: string;
}

export type MainStatus = {
  isBusy: boolean;
  message: string;
}