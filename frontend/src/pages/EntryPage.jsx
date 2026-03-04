import { Link, useParams } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { formatDate, renderMarkdown } from '../lib/markdown.js';

export default function EntryPage({ data }) {
  const { slug } = useParams();
  const entry = data.ENTRIES.find((item) => item.slug === slug);

  if (!entry) {
    return (
      <Layout>
        <p>404 - 文章未找到 <Link to="/">← 返回首页</Link></p>
      </Layout>
    );
  }

  return (
    <Layout>
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
      <Link to="/" className="back-link">← 返回首页</Link>
    </Layout>
  );
}
