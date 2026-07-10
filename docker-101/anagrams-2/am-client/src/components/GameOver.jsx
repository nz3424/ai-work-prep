import PropTypes from 'prop-types';
import "./styles.css";
import { useStateContext } from '../contexts/ContextProvider';

const GameOver = ({ wordBank, score }) => {

    // word bank to be displayed
    // sorted by length, tiebreaker is lexicographic
    const sortedWordBank = Object.keys(wordBank).sort((a, b) =>
        wordBank[b] - wordBank[a] || a.localeCompare(b)
    );
    const { setRoute } = useStateContext();


    return (
        <div className="game-body">
            <div className="score-box">
                <div className="score-box-text">
                    <div>
                        <span className="score-text">Words:</span>
                        <span className="score-text-val">{sortedWordBank.length}</span></div>
                    <div>

                        <span className="score-text">Score:</span>
                        <span className="score-text-val">{score}</span></div>
                </div>
            </div>
            <div className="results">
                <span className="result-title">Results</span>
                {sortedWordBank.map((word) =>
                (<div key={word} className="result-item">
                    <span className="result-item-text">{word.toLowerCase()}</span>
                    <span className="result-item-text" >{wordBank[word]}</span>
                </div>))}
            </div>
            <div style={{ margin: '1vh 0' }}>
                <button className="return-home" onClick={() => setRoute("home")}> Back to Home</button>
            </div>
        </div>
    )
}

GameOver.propTypes = {
    wordBank: PropTypes.objectOf(PropTypes.number).isRequired,
    score: PropTypes.number,
}

export default GameOver