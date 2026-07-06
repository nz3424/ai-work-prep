import { useState, useEffect } from 'react'
import "./styles.css";
import { useStateContext } from '../contexts/ContextProvider';


const SignUp = ({ setIsAuth }) => {
    const [user, setUser] = useState(null);
    const { setActiveUser, setRoute } = useStateContext();
    const defaultActiveUser = { username: "", id: null, friends: [], requests: [], user: { high_score: 0, games_played: 0 } };
    const signUp = () => {
        fetch("http://localhost:3001/signup", {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(user)
        }).then(res => {
            if (!res.ok) throw new Error(`Signup failed: ${res.json().error}`);
            return res.json();
        })
            .then(res => {
                console.log("Response from server on signup: ", res);
                const { token, username, id } = res;
                sessionStorage.setItem("token", token);
                sessionStorage.setItem("username", username);
                sessionStorage.setItem("id", id);
                setIsAuth(true);
                setActiveUser({ ...defaultActiveUser, username: username, id: id });
                setRoute("home");
            })
            .catch(error => {
                console.error("Error during signup: ", error);
                alert("Signup failed");
            });
    };
    // handles key presses
    useEffect(() => {
        const handleKeyDown = (event) => {
            if (event && event.key === "Enter") {
                signUp();
            }
        }
        window.addEventListener("keydown", handleKeyDown);
        handleKeyDown();
        return () => window.removeEventListener("keydown", handleKeyDown);
    }
    );
    return (
        <div className="main-login">
            <label>Sign up</label>
            <div className="login-inputs">
                <input placeholder='username' onChange={(event) => setUser({ ...user, username: event.target.value })}>
                </input>
                <input type="password" placeholder='password' onChange={(event) => setUser({ ...user, password: event.target.value })}>
                </input>
            </div>
            <button className="login-button" type="button" onClick={signUp}>Sign Up</button>
            <div>
                <span className="login-to-signup" >Go back to </span>
                <a onClick={() => { setRoute("login") }}>login</a>
            </div>
        </div>
    )
}

export default SignUp