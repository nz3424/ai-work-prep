
const Card = ({ title, content }) => {
    return (
        <div className="home-card">
            <p className="home-text">{title}</p>
            {content}
        </div>
    )
}

export default Card