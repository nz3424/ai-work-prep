import PropTypes from 'prop-types'

const Card = ({ title, content }) => {
    return (
        <div className="home-card">
            <p className="home-text">{title}</p>
            {content}
        </div>
    )
}

Card.propTypes = {
    title: PropTypes.string,
    content: PropTypes.node,
}

export default Card