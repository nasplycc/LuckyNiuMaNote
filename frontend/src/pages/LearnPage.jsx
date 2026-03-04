import { Link, useParams } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { formatDate, renderMarkdown } from '../lib/markdown.js';

function LearnList({ entries }) {
  return (
    <div className="entries">
      {entries.map((entry) => {
        const preview = entry.content.substring(0, 150).replace(/\*/g, '').replace(/\n/g, ' ');
        return (
          <div className="entry" key={entry.slug}>
            <h2><Link to={`/learn/${entry.slug}`}>{entry.title}</Link></h2>
            <div className="entry-meta">
              📅 {formatDate(entry.date)}
              {entry.tags.map((tag) => <span className="tag" key={`${entry.slug}-${tag}`}>#{tag}</span>)}
            </div>
            <div className="entry-content"><p>{preview}...</p></div>
            <Link to={`/learn/${entry.slug}`} className="read-link">阅读全文 →</Link>
          </div>
        );
      })}
    </div>
  );
}

export default function LearnPage({ data }) {
  const { slug } = useParams();
  const entry = slug ? data.LEARN_ENTRIES.find((item) => item.slug === slug) : null;

  if (slug && !entry) {
    return (
      <Layout>
        <p>404 - 文章未找到 <Link to="/learn">← 返回学习资料</Link></p>
      </Layout>
    );
  }

  return (
    <Layout>
      {entry ? (
        <div className="entry">
          <h2>{entry.title}</h2>
          <p className="entry-meta">
            📅 {formatDate(entry.date)}{' '}
            {entry.tags.map((tag) => <span className="tag" key={tag}>#{tag}</span>)}
          </p>
          <div className="entry-content">
            <p dangerouslySetInnerHTML={{ __html: renderMarkdown(entry.content) }} />
          </div>
        </div>
      ) : (
        <LearnList entries={data.LEARN_ENTRIES} />
      )}
    </Layout>
  );
}
