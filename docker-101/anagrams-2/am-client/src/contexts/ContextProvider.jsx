import React, { createContext, useContext, useEffect, useRef, useState } from 'react';

const StateContext = createContext();

export const ContextProvider = ({ children }) => {

    const [activeUser, setActiveUser] = useState(() => {
        const savedUser = sessionStorage.getItem('activeUser');
        return savedUser ? JSON.parse(savedUser) : null;
    });
    const [route, setRoute] = useState(() => {
        const savedRoute = sessionStorage.getItem('route');
        if (savedRoute === '"game"') {
            return 'home';
        }
        return savedRoute ? JSON.parse(savedRoute) : 'login';
        // make it so if you refresh in the game, it takes you to home

    });


    const [gameMode, setGameMode] = useState("solo");

    const [challengeId, setChallengeId] = useState(null);

    const [letterSet, setLetterSet] = useState(() => {
        const saved = sessionStorage.getItem('letterSet');
        return saved ? JSON.parse(saved) : null;
    });

    // retry state
    const [sseRetry, setSseRetry] = useState(0);

    const eventSourceRef = useRef(null);

    // Fetch latest user data from /me and update activeUser in context
    const refreshUser = () => {
        const token = sessionStorage.getItem("token");
        if (!token) return;
        fetch("http://localhost:3001/me", {
            headers: { Authorization: `Bearer ${token}` }
        })
            .then(res => res.json())
            .then(data => {
                setActiveUser(prev => ({ ...prev, ...data }));
            })
            .catch(err => console.error("Failed to refresh user:", err));
    };

    // Open SSE connection whenever the user logs in, close it on logout
    useEffect(() => {
        const token = sessionStorage.getItem("token");

        if (!activeUser || !token) {
            // User logged out — close any open SSE connection
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
                eventSourceRef.current = null;
            }
            return;
        }

        // Don't open a duplicate connection
        if (eventSourceRef.current) return;

        // EventSource doesn't support custom headers, so we pass the token as a
        // query param. Make sure authenticateToken on the server also checks for
        // req.query.token as a fallback
        const es = new EventSource(`http://localhost:3001/events?token=${token}`);
        eventSourceRef.current = es;

        // Opponent finished their challenge game → our record updated
        es.addEventListener('record_updated', () => {
            console.log("Received record_updated event");
            refreshUser();
        });

        // Someone sent us a friend request
        es.addEventListener('friend_request', () => {
            console.log("Received/accepted friend request event");
            refreshUser();
        });

        // Someone sent us a challenge
        es.addEventListener('new_challenge', () => {
            console.log("Received new challenge event");
            refreshUser();
        });

        // Later: Can add something like "challenge complete" that pops up a thing that says "Your friend X completed the challenge you sent them! Want to play again?" with a button that starts a new challenge with them

        // Auto-reconnect on error after 3 seconds
        es.onerror = () => {
            es.close();
            eventSourceRef.current = null;
            setTimeout(() => setSseRetry(prev => prev + 1), 3000); // rerun useEffect to reconnect
        };

        return () => {
            es.close();
            eventSourceRef.current = null;
        };
    }, [activeUser, sseRetry]);

    useEffect(() => {
        sessionStorage.setItem('activeUser', JSON.stringify(activeUser));
        sessionStorage.setItem('route', JSON.stringify(route));
    }, [route, activeUser]);

    return (<StateContext.Provider value={{ activeUser, setActiveUser, route, setRoute, gameMode, setGameMode, challengeId, setChallengeId, letterSet, setLetterSet, refreshUser }}
    >
        {children}
    </StateContext.Provider>)

}
export const useStateContext = () => useContext(StateContext);