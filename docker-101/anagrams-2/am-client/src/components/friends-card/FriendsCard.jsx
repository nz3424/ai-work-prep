import { useState, useEffect } from "react";
import PropTypes from "prop-types";
import Card from "../Card";
import "./friends-card.css";
import { useStateContext } from '../../contexts/ContextProvider';
import { letterSets, API_BASE_URL } from '../../constants';

const FriendsCard = ({ friends, requests }) => {
    const [isFriendView, setIsFriendView] = useState(true);
    const [modalOpen, setModalOpen] = useState(false);
    const [friendSearch, setFriendSearch] = useState("");
    const { setRoute, setGameMode, setChallengeId, setLetterSet, refreshUser } = useStateContext();
    useEffect(() => {
        const handleKeyDown = (event) => {
            if (event && event.key === "Enter") {
                addFriend(friendSearch);


            }
        }
        window.addEventListener("keydown", handleKeyDown);
        handleKeyDown();
        return () => window.removeEventListener("keydown", handleKeyDown);
    }
    );
    const addFriend = (username) => {
        fetch(`${API_BASE_URL}/friend-request`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                authorization: `Bearer ${sessionStorage.getItem("token")}`,
            },
            body: JSON.stringify({ username })
        }).then(res => {
            console.log("Response from server: ", res);
            if (!res.ok) throw new Error(`Failed to send friend request: ${res.json().error}`);

            alert("Friend request sent"); // make this better 
            // clear input field if successful
            setFriendSearch("");
            return res.json();
        }).catch(error => {
            console.error("Error sending friend request: ", error);
            alert("Failed to send friend request");
        })
    }

    const acceptRequest = (requester) => {
        console.log("Accepting request from: ", requester.requester_name);
        // then remove request from list? (or is this already handled)
        fetch(`${API_BASE_URL}/friends/accept`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                authorization: `Bearer ${sessionStorage.getItem("token")}`,

            },
            body: JSON.stringify({ requester_id: requester.requester_id })
        }).then(async res => {
            const data = await res.json()
            if (!res.ok) throw new Error(`Failed to accept friend request: ${res.json().error}`);
            refreshUser();
            setIsFriendView(true);
            return data;
        }).catch(error => {
            console.error("Error accepting friend request: ", error);
            alert("Failed to accept friend request");
        })
    };

    const declineRequest = (requester) => {
        console.log("Declining request from: ", requester);
        fetch(`${API_BASE_URL}/friends/decline`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                authorization: `Bearer ${sessionStorage.getItem("token")}`,

            },
            body: JSON.stringify({ requester_id: requester.requester_id })
        }).then(async res => {
            const data = await res.json()
            if (!res.ok) throw new Error(`Failed to decline friend request: ${res.json().error}`);
            refreshUser();
            return data;
        }).catch(error => {
            console.error("Error declining friend request: ", error);
            alert("Failed to decline friend request");
        })
    };

    const sendChallenge = (friend) => {
        console.log("Sending challenge to: ", friend);
        // start a game with this friend
        fetch(`${API_BASE_URL}/challenge`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${sessionStorage.getItem("token")}`,
            },
            body: JSON.stringify({
                friend_id: friend.id
            })
        }).then(async res => {
            const data = await res.json()
            if (!res.ok) throw new Error(`Failed to send challenge: ${data.error}`);
            console.log("Challenge sent to : ", friend.username);
            setChallengeId(data.challengeId);
            setRoute("game");
            setGameMode("challenge");
            setLetterSet(letterSets[Math.floor(Math.random() * letterSets.length)]);
            return data;
        }).catch(error => {
            console.error("Error sending challenge: ", error);
            alert("Failed to send challenge");
        });


    }

    const content =
        <div className="friends-container">
            <div className="friends-header">
                <p className="friends-text">Manage friends and challenges</p>
                <button onClick={() => setModalOpen(true)}>Add friends</button>
            </div>

            <div className="friends-body">
                <div className="toggle-container">
                    <button className={isFriendView ? "clicked-toggle" : "unclicked-toggle"} onClick={() => setIsFriendView(true)}>Friends</button>
                    <button className={isFriendView ? "unclicked-toggle" : "clicked-toggle"} onClick={() => setIsFriendView(false)}>Requests</button>
                </div>
                <div className="friends-list">
                    {isFriendView ?
                        (friends && friends.length > 0 ? friends.map((friend, index) => (
                            <div className="friends-row-container" key={index} ><p className="friends-text">{friend.username}</p>
                                <button key={index} className="friends-challenge" onClick={() => sendChallenge(friend)}>Challenge!</button></div>
                        )) : <p className="friends-text">You have no friends added</p>)
                        :
                        (requests && requests.length > 0 ? requests.map((request, index) => (
                            <div key={index} className="friend-request">
                                <p className="friends-text">{request.requester_name}</p>
                                <div className="friend-request-buttons">
                                    <button onClick={() => { acceptRequest(request) }}>Accept</button>
                                    <button onClick={() => { declineRequest(request) }}>Decline</button>
                                </div>
                            </div>
                        )) : <p className="friends-text">You have no pending requests</p>)
                    }
                </div>
            </div>
        </div>
    return (
        <>
            <Card
                title="Friends"
                content={content}
            />
            {modalOpen &&
                <div>
                    <dialog open onClose={() => setModalOpen(false)} className="friends-dialog">
                        <div className="top-row">
                            <p>Add friend</p>
                            <button className="modal-close" onClick={() => setModalOpen(false)}>X</button>
                        </div>

                        <div className="input-container">
                            <input className="friends-input" type="text" placeholder="Enter username" value={friendSearch} onChange={(event) => setFriendSearch(event.target.value)}>
                            </input>
                            <button className="friends-button" onClick={() => {
                                addFriend(friendSearch);
                            }}>{">"}</button>
                        </div>
                    </dialog>
                    <div className="overlay" onClick={() => {
                        setModalOpen(false);
                    }} />
                </div>}
        </>

    )
}

FriendsCard.propTypes = {
    friends: PropTypes.arrayOf(PropTypes.shape({
        username: PropTypes.string,
        id: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    })),
    requests: PropTypes.arrayOf(PropTypes.shape({
        requester_name: PropTypes.string,
        requester_id: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    })),
}

export default FriendsCard