
const fs = require("fs")
const { lstatSync, readdirSync } = require("fs")
const path = require("path")

async function asyncForEach(array, callback) {
  for (let index = 0; index < array.length; index++) {
    await callback(array[index], index, array);
  }
}

function pad(num, size) {
  num = num.toString();
  while (num.length < size) num = "0" + num;
  return num;
}

function readableDate(timestamp){
  const d = new Date(parseInt(timestamp));
  return `${d.getMonth()+1}-${d.getDate()}-${d.getFullYear()}`
}

function objectsMatch(obj1,obj2){
  if( Object.keys(obj1).length != Object.keys(obj2).length) return false
  let match = true;
  Object.keys(obj1).forEach(key => {
    if(obj2[key] != obj1[key] ) match = false
  })
  return match
}

function shuffleArray(_array) {
  const array = _array.slice(0)
  var currentIndex = array.length, temporaryValue, randomIndex;

  // While there remain elements to shuffle...
  while (0 !== currentIndex) {

    // Pick a remaining element...
    randomIndex = Math.floor(Math.random() * currentIndex);
    currentIndex -= 1;

    // And swap it with the current element.
    temporaryValue = array[currentIndex];
    array[currentIndex] = array[randomIndex];
    array[randomIndex] = temporaryValue;
  }
  return array;
}


module.exports = {
  asyncForEach,
  pad,
  readableDate,
  objectsMatch,
  shuffleArray,
}
