// static/js/quiz.js
(function() {
  const { useState, useEffect } = React;
  const ReactDOM = window.ReactDOM;

  function Quiz({ questions }) {
    const [answers, setAnswers] = useState({});
    const handleChange = (qnum, choice) => {
      setAnswers(prev => ({ ...prev, [qnum]: choice }));
    };

    const answeredCount = Object.keys(answers).length;
    const total = questions.length;

    useEffect(() => {
      const input = document.getElementById('answers-input');
      if (input) input.value = JSON.stringify(answers);
    }, [answers]);

    return React.createElement(
      React.Fragment,
      null,
      React.createElement(
        'div',
        { className: 'progress mb-3' },
        React.createElement('div', {
          className: 'progress-bar',
          role: 'progressbar',
          style: { width: `${(answeredCount/total)*100}%` },
          'aria-valuenow': answeredCount,
          'aria-valuemin': 0,
          'aria-valuemax': total,
        }),
        React.createElement(
          'span',
          { className: 'ms-2' },
          `${answeredCount} of ${total} answered`
        )
      ),
      questions.map((q, idx) =>
        React.createElement(
          'div',
          {
            key: q.qnum,
            className: `card mb-4 ${answers[q.qnum] ? '' : 'bg-light'}`,
            id: `q-${q.qnum}`,
          },
          React.createElement(
            'div',
            { className: 'card-body' },
            React.createElement(
              'p',
              { className: 'card-text' },
              React.createElement('strong', null, `${idx + 1}. `),
              React.createElement('span', {
                dangerouslySetInnerHTML: { __html: q.question_text },
              })
            ),
            React.createElement(
              'div',
              { className: 'list-group' },
              ['A','B','C','D'].map(opt =>
                React.createElement(
                  'label',
                  {
                    key: opt,
                    className: 'list-group-item list-group-item-action',
                  },
                  React.createElement('input', {
                    type: 'radio',
                    name: `q_${q.qnum}`,
                    value: opt,
                    className: 'form-check-input me-2',
                    checked: answers[q.qnum] === opt,
                    onChange: () => handleChange(q.qnum, opt),
                  }),
                  React.createElement('span', {
                    dangerouslySetInnerHTML: { __html: q[`option_${opt.toLowerCase()}`] },
                  })
                )
              )
            ),
          )
        )
      )
    );
  }

  document.addEventListener('DOMContentLoaded', () => {
    // 1) Grab & parse the JSON from the <script> tag
    const script = document.getElementById('questions-data');
    let questions = [];
    try {
      questions = JSON.parse(script.textContent);
    } catch (e) {
      console.error('Could not parse questions JSON:', script.textContent, e);
      return;
    }

    // 2) Find the container
    const rootEl = document.getElementById('quiz-root');
    if (!rootEl) return;

    // 3) Use React 18 createRoot API
    const root = ReactDOM.createRoot(rootEl);
    root.render(
      React.createElement(Quiz, { questions })
    );
  });

})();
