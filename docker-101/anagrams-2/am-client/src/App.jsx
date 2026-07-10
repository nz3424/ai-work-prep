import { useState, useEffect } from 'react'
import { useStateContext } from './contexts/ContextProvider';


import { Home, Game, Login, SignUp } from './components';
import { API_BASE_URL } from './constants';

export default function App() {
    const size = 6;
    const token = sessionStorage.getItem("token");
    const [, setIsAuth] = useState(false);

    const { activeUser, setActiveUser, route, gameMode, letterSet } = useStateContext();
    // connect user to account
    useEffect(() => {
        if (token) {
            fetch(`${API_BASE_URL}/me`, {
                method: "GET",
                headers: {
                    Authorization: `Bearer ${token}`
                }
            })
                .then(res => {
                    if (!res.ok) throw new Error("Invalid token");
                    return res.json();
                })
                .then(data => {
                    console.log("Fetched user data: ", data);
                    const user = data;
                    setIsAuth(true);
                    setActiveUser({ ...activeUser, ...user });
                    console.log("User data fetched: ", user);
                    // Save other user data you want to state if needed
                })
                .catch(() => {
                    // Token invalid or expired — force logout or clear storage
                    sessionStorage.removeItem("token");
                    setIsAuth(false);
                });
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally only re-runs when the token changes
    }, [token]);

    const logout = () => {
        sessionStorage.removeItem("token");
        sessionStorage.removeItem("username");
        sessionStorage.removeItem("id");
        setIsAuth(false);
        setActiveUser(null);
    }

    switch (route) {
        case "login":
            return <Login setIsAuth={setIsAuth} />;
        case "signup":
            return <SignUp setIsAuth={setIsAuth} />;
        case "home":
            return <Home onLogout={logout} />;
        case "game":
            return <Game size={size} mode={gameMode} letterSet={letterSet} />;
        default:
            return <Login setIsAuth={setIsAuth} />;
    }

}
