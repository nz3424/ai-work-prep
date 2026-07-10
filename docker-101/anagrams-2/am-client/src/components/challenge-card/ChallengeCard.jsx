import PropTypes from "prop-types";
import Card from "../Card";
import "./challenge-card.css";
import { useStateContext } from '../../contexts/ContextProvider';
import { API_BASE_URL } from '../../constants';

const ChallengeCard = ({ challenges }) => {
    const { setRoute, setGameMode, setChallengeId, setLetterSet } = useStateContext();

    function timeAgo(dateString) {
        const now = new Date();
        const date = new Date(dateString);
        const diffMs = now - date;
        const diffSec = Math.floor(diffMs / 1000);
        const diffMin = Math.floor(diffSec / 60);
        const diffHr = Math.floor(diffMin / 60);
        const diffDay = Math.floor(diffHr / 24);

        if (diffDay > 0) return `${diffDay} day${diffDay > 1 ? "s" : ""} ago`;
        if (diffHr > 0) return `${diffHr} hour${diffHr > 1 ? "s" : ""} ago`;
        if (diffMin > 0) return `${diffMin} minute${diffMin > 1 ? "s" : ""} ago`;
        return "Just now";
    }

    const handleChallengeAccept = (challengeId) => {
        fetch(`${API_BASE_URL}/challenges/${challengeId}/accept`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${sessionStorage.getItem("token")}`,
            }
        }).then(async res => {
            console.log("Accept challenge response status: ", res.status);
            if (res.status === 403) {
                // Token invalid or expired — force logout or clear storage
                console.error("Token invalid or expired. Logging out.");
                sessionStorage.removeItem("token");
                setRoute("login");
                return;
            }
            const data = await res.json()
            console.log("Accept challenge response data: ", data);

            if (!res.ok) throw new Error(`Failed to accept challenge: ${data.error}`);

            setChallengeId(data.challengeId);
            setLetterSet(data.letterSet.split(""));
            sessionStorage.setItem('letterSet', JSON.stringify(data.letterSet));
            // Accept challenge logic here
            setGameMode("challenge");
            setRoute("game");
            return data;
        }).catch(error => {
            console.error("Error accepting challenge: ", error);
        })

    }
    const content =
        <div className="challenges-container">
            {(challenges && challenges.length > 0 ? challenges.map((challenge, index) => (
                <div key={index} className="challenge-row">
                    <div className="left-container">
                        <p className="challenge-text">{challenge.challenger_username}</p>
                        <p className="challenge-subtext">{timeAgo(challenge.created_at)} </p>
                    </div>
                    <div className="right-container">
                        <button onClick={() => handleChallengeAccept(challenge.id)}>Accept</button>
                    </div>
                </div>
            )) : <p className="challenge-text">You have no pending challenges</p>)}
        </div>
    return (
        <Card
            title="Challenges"
            content={content}
        />
    )
}

ChallengeCard.propTypes = {
    challenges: PropTypes.arrayOf(PropTypes.shape({
        id: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
        challenger_username: PropTypes.string,
        created_at: PropTypes.string,
    })),
}

export default ChallengeCard