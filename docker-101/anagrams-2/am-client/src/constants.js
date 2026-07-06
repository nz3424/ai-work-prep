
export const API_URL = 'https://wordsapiv1.p.rapidapi.com/words/';

export const scores = {
    3: 200,
    4: 400, 5: 1200, 6: 2000,
}


export const options = {
    method: 'GET',
    headers: {
        'X-RapidAPI-Key': 'b274a32761msh9b9458310db65bfp1f0907jsn46cfa24f5e08',
        'X-RapidAPI-Host': 'wordsapiv1.p.rapidapi.com'
    }
};

export const letterSets = [
    ["A", "S", "T", "E", "T", "R"], ["N", "M", "A", "E", "I", "R"], ["P", "L", "T", "E", "C", "A"],
    ["O", "P", "U", "E", "T", "R"], ["R", "S", "S", "E", "U", "C"], ["B", "K", "I", "M", "C", "N"],
    ["V", "E", "N", "T", "O", "R"], ["D", "E", "A", "L", "I", "N"], ["H", "I", "G", "T", "R", "E"],
    ["F", "A", "C", "E", "T", "R"], ["L", "I", "G", "H", "T", "S"], ["C", "R", "A", "T", "E", "S"],
    ["T", "A", "B", "L", "E", "S"], ["S", "N", "O", "R", "T", "E"], ["D", "I", "N", "E", "R", "S"],
    ["G", "A", "R", "D", "E", "N"], ["C", "O", "A", "S", "T", "E"], ["F", "O", "R", "C", "E", "T"],
    ["M", "A", "R", "K", "E", "T"], ["L", "A", "T", "E", "R", "S"]
].map(set => {
    const arr = [...set];
    for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
});


