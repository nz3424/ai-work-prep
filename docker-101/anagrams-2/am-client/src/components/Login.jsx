import { useState, useEffect } from 'react'
import "./styles.css";
import { useStateContext } from '../contexts/ContextProvider';
import { API_BASE_URL } from '../constants';


const Login = ({ setIsAuth }) => {
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");

    const { activeUser, setActiveUser, setRoute } = useStateContext();
    const login = () => {
        fetch(`${API_BASE_URL}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        }).then((res) => {
            if (!res.ok) throw new Error(`Login failed: ${res.statusText}`);
            return res.json();
        }).then((res) => {
            console.log("Response from server ", res);
            const { token, username, id } = res;
            sessionStorage.setItem("token", token);
            sessionStorage.setItem("username", username);
            sessionStorage.setItem("id", id);
            setIsAuth(true);
            setActiveUser({ ...activeUser, username: username, id: id });
            setRoute("home");
        }).catch(error => {
            console.log("Error during login: ", error);
            alert("Login failed. Please check your username and password.");
        });
    }
    // handles key presses
    useEffect(() => {
        const handleKeyDown = (event) => {
            if (event && event.key === "Enter") {
                login();
            }
        }
        window.addEventListener("keydown", handleKeyDown);
        handleKeyDown();
        return () => window.removeEventListener("keydown", handleKeyDown);
    }
    );
    return (
        <div className="main-login">
            <label>Login</label>
            <div className="login-inputs">
                <input placeholder='username' onChange={(event) => setUsername(event.target.value)}>
                </input>
                <input type="password" placeholder='password' onChange={(event) => setPassword(event.target.value)}>
                </input>
            </div>
            <button className="login-button" type="button" onClick={() => { login() }}>Login</button>
            <div>
                <span className="login-to-signup" >Don't have an account? Sign up </span>
                <a onClick={() => { setRoute("signup") }}>here</a>
            </div>

        </div>
    )
}

export default Login