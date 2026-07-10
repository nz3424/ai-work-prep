import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { FaBackspace } from "react-icons/fa";
import { FaShuffle } from "react-icons/fa6"
import GameOver from './GameOver';
import { scores, options, API_URL, API_BASE_URL } from "../constants";
import { useStateContext } from '../contexts/ContextProvider';
export default function Game({ letterSet, size = 6, mode = "solo" }) {

    // *ordered* set of letters displayed
    const [letters, setLetters] = useState(letterSet);

    // array of indices of letters currently displayed (index in letters)
    const [display, setDisplay] = useState(Array(size).fill(null));

    // array of whether input buttons (bottom) are active or inactive
    const [inputClasses, setInputClasses] = useState(Array(size).fill(true));

    // length of current string
    const [currLength, setCurrLength] = useState(0);

    // current word, score
    const [currWord, setCurrWord] = useState("");
    const [score, setScore] = useState(0);

    // sets the feedback after submitting a word
    const [feedback, setFeedback] = useState("inactive");
    const [feedbackMessage, setFeedbackMessage] = useState("");

    // all words seen so far
    // format: key: word, value: score
    const [wordBank, setWordBank] = useState({});

    const { activeUser, setGameMode, refreshUser, setChallengeId, challengeId, setLetterSet } = useStateContext();
    // format: {letter: [# of occurences, <indices of letter>]}
    // to access: 
    // desired index: availLetters[<letter>][0]
    // syntax: availLetters[<letter>][availLetters[<letter>][0]]
    // handling: Change desired index to change position
    const initialAvailLetters = {};
    for (let i = 0; i < letters.length; i++) {
        const letter = letters[i].toUpperCase();
        if (!(letter in initialAvailLetters))
            initialAvailLetters[letter] = [1, i];
        else {
            initialAvailLetters[letter].push(i);
        }
    }
    const [availLetters, setAvailLetters] = useState(initialAvailLetters);


    // time
    const [time, setTime] = useState(10);


    // timer, countsdown from time to 0
    useEffect(() => {
        if (time > 0) {
            const interval = setInterval(() => setTime(time - 1, 0), 1000);
            return () => clearInterval(interval);
        }
    }, [time]);

    // backspace function
    const onBackspace = () => {
        if (currLength >= 1) {

            const prevDisplay = display.slice();
            const deletedIdx = prevDisplay[currLength - 1];
            prevDisplay[currLength - 1] = null;
            setDisplay(prevDisplay);

            const letter = letters[deletedIdx];
            const prevInputClasses = inputClasses.slice();
            const index = availLetters[letter][availLetters[letter][0] - 1];
            if (availLetters[letter][0] > 2 || availLetters[letter][0] < availLetters[letter].length) {
                prevInputClasses[index] = true;
            }
            else {
                // only one occurrance of the letter (I think)
                prevInputClasses[deletedIdx] = true;
            }
            //  prevInputClasses[deletedIdx] = true;
            setInputClasses(prevInputClasses);

            setCurrLength(currLength - 1);

            //   update availLetters by decrementing index by 1
            let newVal = availLetters[letter].slice();
            newVal[0] -= 1;
            setAvailLetters({ ...availLetters, [letter]: newVal });
        }
    }


    // shuffles the letters, clears the board
    const onShuffle = () => {
        let newLetters = letters.slice().sort(() => Math.random() - 0.5);
        setLetters(newLetters);
    }

    // changes the underlying settings after the shuffle
    useEffect(() => {
        const shuffleReset = () => {
            // reset
            setInputClasses(Array(size).fill(true));
            setCurrLength(0);
            setCurrWord("");
            setDisplay((Array(size).fill(null)));

            // format: {letter: [# of occurences, <indices of letter>]}
            // to access
            let initial = {};
            for (let i = 0; i < letters.length; i++) {
                const letter = letters[i].toUpperCase();
                if (!(letter in initial))
                    initial[letter] = [1, i];
                else {
                    initial[letter].push(i);
                }
            }
            setAvailLetters(initial);
        }
        shuffleReset();
    }, [letters, size]);

    // handles key presses
    useEffect(() => {
        const handleKeyDown = (event) => {
            if (event) {
                // valid letter
                if (letters.includes(event.key.toUpperCase())) {
                    const letter = event.key.toUpperCase();
                    // check to make sure all of this letter hasn't been used up
                    if (availLetters[letter][0] < availLetters[letter].length) {
                        const prevDisplay = display.slice();
                        const prevInputClasses = inputClasses.slice();

                        // set clicked letter to inactive, update display index
                        let index = availLetters[letter][availLetters[letter][0]];
                        prevInputClasses[index] = false;
                        prevDisplay[currLength] = index;
                        // update length
                        setCurrLength(currLength + 1);

                        // update input classes and display
                        setInputClasses(prevInputClasses);
                        setDisplay(prevDisplay);
                        let newVal = availLetters[letter].slice();
                        newVal[0] += 1;
                        setAvailLetters({ ...availLetters, [letter]: newVal });
                    }
                }
                // delete button
                else if (event.key === "Backspace") {
                    onBackspace();
                }
                else if (event.key === "Enter") {
                    onSubmit();
                }
            }
        }

        window.addEventListener("keydown", handleKeyDown);
        handleKeyDown();
        return () => window.removeEventListener("keydown", handleKeyDown);
    }
    );

    // handles clicking on the big letters at the top
    // Purpose: Deletes the letter and (if neccessary) shifts the letters
    const handleDisplayClick = (clickedIndex) => {
        if (currLength > 0 && display[clickedIndex] !== null) {
            let prevDisplay = display.toSpliced(clickedIndex, 1);
            prevDisplay.push(null);

            const letter = letters[display[clickedIndex]];

            // if repeat, get the largest index of the clicked letter
            const index = availLetters[letter][availLetters[letter][0] - 1];

            const prevInputClasses = inputClasses.slice();
            if (availLetters[letter][0] > 2 || availLetters[letter][0] < availLetters[letter].length) {
                prevInputClasses[index] = true;
            }
            else
                prevInputClasses[display[clickedIndex]] = true;

            console.log(prevDisplay);
            // issue: figure out how to update availLetters when something IN THE MIDDLE is clicked
            let newVal = availLetters[letter].slice();
            newVal[0] -= 1;
            console.log(newVal);

            setDisplay(prevDisplay);
            setCurrLength(currLength - 1);
            setInputClasses(prevInputClasses);
            setAvailLetters({ ...availLetters, [letter]: newVal });
        }
    }

    // handles clicking on the input letters at the bottom
    const handleInputClick = (clickedIndex) => {
        console.log(clickedIndex);
        // create copies
        const prevDisplay = display.slice();
        const prevInputClasses = inputClasses.slice();

        // set clicked letter to inactive, update display index
        prevInputClasses[clickedIndex] = false;
        prevDisplay[currLength] = clickedIndex;

        let newVal = availLetters[letters[clickedIndex]].slice();
        newVal[0] += 1;
        setAvailLetters({ ...availLetters, [letters[clickedIndex]]: newVal });

        // update length
        setCurrLength(currLength + 1);

        console.log(prevDisplay);
        console.log(newVal);
        // update input classes and display
        setInputClasses(prevInputClasses);
        setDisplay(prevDisplay);

    }


    const resetBoard = () => {
        setAvailLetters(initialAvailLetters);
        setDisplay(Array(size).fill(null));
        setInputClasses(Array(size).fill(true));
        setCurrWord("");
        setCurrLength(0);
    }
    // handles submitting or clicking enter 
    // Purpose: Check if word is valid, 


    // CURRENT BUG: if clicks are used at all, it gets fucked up when you type enter
    const onSubmit = () => {
        if (currLength >= 3) {
            const word = display.map((index) => letters[index]).join("");
            setCurrWord(word);

        }
        setTimeout(() => {
            resetBoard();
            setFeedback("inactive");
        }, 750)
    }

    // check valid word when currWord changes

    const updateScore = (correct) => {
        setFeedback("active")
        if (correct) {
            setScore(score + scores[currLength]);
            setWordBank({ ...wordBank, [currWord]: scores[currLength] });
            setFeedbackMessage(`${currWord} +${scores[currLength]}`);
        }
        else {
            setFeedbackMessage("Word has already been used");
        }
    }

    // checks if word is valid
    useEffect(() => {
        const fetchWord = async () => {
            await fetch(`${API_URL}${currWord.toLowerCase()}/definitions`, options)
                .then(response => response.json())
                .then(data => {
                    if (data.word) {
                        if (!(currWord in wordBank)) {
                            updateScore(true, data.word);
                        }
                        else {
                            updateScore(false, data.word);
                        }
                    }
                    else if (data.success === false) {
                        setFeedback("active");
                        setFeedbackMessage("Not a word");

                    }
                }).catch(err => {
                    console.error(err);
                });
        };
        fetchWord()
        // eslint-disable-next-line react-hooks/exhaustive-deps -- adding updateScore/wordBank would refetch on every score update
    }, [currWord])


    const endGame = (score) => {
        fetch(`${API_BASE_URL}/score`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${sessionStorage.getItem("token")}`
            },
            body: JSON.stringify({
                score: score,
                user: activeUser,
                letter_set: letterSet.sort().join(""),
                mode: mode,
                challengeId: mode === "challenge" ? challengeId : null
            })
        }).then(res => {
            if (!res.ok) throw new Error(`Score submission failed: ${res.statusText}`);
            return res.json();
        })
            .then(res => {
                console.log("Response from server on score submission: ", res);
                // reset game states
                setGameMode("solo");
                setChallengeId(null);
                refreshUser();
                sessionStorage.removeItem("letterSet");
                setLetterSet(null);
            })
            .catch(error => {
                console.error("Error during score submission: ", error);
                alert("Score submission failed");
            })
    }
    // handles game completion
    useEffect(() => {
        if (time === 0) {
            setFeedback("inactive");
            setTime(null);
            endGame(score);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps -- endGame closes over state that would retrigger this effect if included
    }, [time, score]);

    return (
        <div className="game-body">
            {time ? <><div className="score-main">
                <span >Score: </span>
                <span className="score-val">{score}</span>
            </div>
                <div>
                    <span className="time">{`Time: ${time}s`}</span>
                </div>
                <div className={`feedback-${feedback}`}>
                    <span>{feedback === "active" ? feedbackMessage : ""}</span>
                </div>
                <div className="flex-letters">
                    {letters.map((letter, idx) => (
                        <button key={idx} type="button"
                            onClick={() => handleDisplayClick(idx)}
                            className={display[idx] !== null ? "active-display-letter"
                                : "display-letter"}>
                            {(display[idx] !== null) && letters[display[idx]]}
                        </button>
                    ))}
                </div>

                <div className="flex-letters">
                    {letters.map((letter, idx) => (
                        <button key={idx} type="button" onClick={inputClasses[idx] ? () => handleInputClick(idx) : () => { }} className={inputClasses[idx] ? "active-input-letter"
                            : "input-letter"}>{inputClasses[idx] && letter}</button>
                    ))}
                </div>
                <div className="actions">
                    <button type="button" className="submit" onClick={onSubmit}>Submit</button>
                    <button type="button" className="backspace" onClick={onBackspace}>
                        <span type="icon"><FaBackspace size={25} /></span>
                    </button>
                </div>
                <div className="actions"> <button type="button" className="shuffle" onClick={onShuffle}>
                    <span type="icon"><FaShuffle size={25} /></span>
                </button>


                </div></>
                : <div>
                    <GameOver wordBank={wordBank} score={score} />
                </div>}
        </div >
    )
}

Game.propTypes = {
    letterSet: PropTypes.arrayOf(PropTypes.string).isRequired,
    size: PropTypes.number,
    mode: PropTypes.string,
}
