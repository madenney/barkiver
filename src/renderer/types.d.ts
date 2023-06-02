
export type Match = {
    player1:  string;
    player2: string;
    matchLink:  string;
    videoLink:  string;
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
}

export type Player = {
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
  slice: number;
  shuffle: boolean;
  sortParam: string;
  players: Array<Player>;
  custom: boolean;
  startSeconds: number;
  endSeconds: number;
  HQMode: boolean;
  removeOverlap: boolean;
}