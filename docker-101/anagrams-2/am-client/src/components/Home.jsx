import React, { useEffect, useState } from 'react';
import "./styles.css";
import { useStateContext } from '../contexts/ContextProvider';
import Card from './Card';
import FriendsCard from './friends-card/FriendsCard';
import { ChallengeCard } from './challenge-card';
import { PlayNowCard } from './play-now-card';
import { GameLogCard } from './game-log-card';
import { letterSets } from '../constants';
import Game from './Game';

export default function Home({ onLogout }) {
    const { activeUser, setRoute, setGameMode, setLetterSet, setChallengeId } = useStateContext();
    if (!activeUser) {
        return;
    }
    const logout = () => {
        onLogout();
        setRoute('login');
    }

    return (
        <div className="home-container">
            <div className="home-header">
                <div className="home-text">Anagrams</div>
                <div className="user-headline">
                    <div className="home-text user">
                        <p>{activeUser.username}</p>
                    </div>
                    <button
                        onClick={() => logout()}>Logout</button>
                </div>
            </div>
            <div className="home-body">
                <div className="home-grid-container">
                    <PlayNowCard />
                </div>
                <div className="home-grid-container">
                    {<ChallengeCard challenges={activeUser.challenges} />}
                    <FriendsCard friends={activeUser.friends} requests={activeUser.requests} />
                </div>

                <div className="home-grid-container">
                    <Card title="Your Statistics" content={
                        <div style={{ width: '100%' }}>
                            <div className="stats-text">
                                <p className="home-text-label">Record:</p>
                                <p>{activeUser.wins} - {activeUser.losses}</p>
                            </div>
                            <div className="stats-text">
                                <p className="home-text-label">Highest Score:</p>

                                <p>{activeUser.high_score}</p>
                            </div>
                            <div className="stats-text"><p className="home-text-label">Games played:</p>
                                <p>{activeUser.games_played}</p>
                            </div>
                        </div>} />
                    <Card title="Game Log" content={
                        <GameLogCard />
                    } />
                </div>
            </div >
        </div >
    )
}
