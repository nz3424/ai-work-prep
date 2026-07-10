import { useState } from "react";
import Card from "../Card";
import "./play-now-card.css";
import { useStateContext } from '../../contexts/ContextProvider';
import { letterSets, API_BASE_URL } from "../../constants";
const PlayNowCard = () => {
    const { activeUser, setRoute, gameMode, setGameMode, setChallengeId, setLetterSet } = useStateContext();

    const [selectedFriend, setSelectedFriend] = useState(null);
    console.log("Selected friend: ", selectedFriend);

    const handleSelection = (e) => {
        if (e.target.value === "solo") {
            setGameMode("solo");
            setChallengeId(null);
        } else {
            setGameMode("challenge");
            setChallengeId(null);
            setSelectedFriend(e.target.value);
        }
    }

    const sendChallenge = (id) => {
        console.log("Sending challenge to: ", id);
        // start a game with this friend
        fetch(`${API_BASE_URL}/challenge`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${sessionStorage.getItem("token")}`,
            },
            body: JSON.stringify({
                friend_id: id
            })
        }).then(async res => {
            const data = await res.json()
            if (!res.ok) throw new Error(`Failed to send challenge: ${data.error}`);
            setChallengeId(data.challengeId);
            setRoute("game");
            setGameMode("challenge");
            return data;
        }).catch(error => {
            console.error("Error sending challenge: ", error);
            alert("Failed to send challenge");
        });
    }

    const content =
        <div className="play-now-container">
            <div className="game-mode-container">
                <p className="play-now-text">Select game mode</p>
            </div>
            <div className="select-container">
                <select
                    onChange={(e) => handleSelection(e)}
                    defaultValue="solo"
                >
                    <option className="solo-select" value="solo">Solo</option>
                    {activeUser.friends && activeUser.friends.map(friend => <option className="challenge-select" value={friend.id} key={friend.id}>Challenge {friend.username} </option>)}
                </select>
            </div>
            <button
                onClick={() => {
                    setLetterSet(letterSets[Math.floor(Math.random() * letterSets.length)]);
                    setRoute("game");
                    if (gameMode === "challenge") {
                        sendChallenge(selectedFriend);
                    }
                }
                }>Start game</button>
        </div>
    return (
        <Card
            title="Play Now"
            content={content}
        />
    )
}

export default PlayNowCard