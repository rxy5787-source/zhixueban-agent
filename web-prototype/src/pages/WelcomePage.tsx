import { Icon } from '../components/Icon'

export function WelcomePage({ onStart }: { onStart: () => void }) {
  return <div className="welcome-page page-enter">
    <section className="welcome-hero" aria-labelledby="welcome-title">
      <div className="welcome-copy">
        <div className="editorial-label"><span/>AI 学习工作台</div>
        <h1 id="welcome-title">读懂资料，<br/>练到掌握。</h1>
        <p>从一份学习资料开始。提问、整理知识点，或生成一组练习。</p>
        <button className="primary-button welcome-start" onClick={onStart}>开始学习<Icon name="arrow" size={19}/></button>
      </div>
      <div className="reading-art" aria-hidden="true">
        <span className="reading-orbit"/>
        <span className="reading-sheet reading-sheet--back"/>
        <span className="reading-sheet reading-sheet--front"><i/><i/><i/><i/></span>
        <span className="reading-volume">
          <Icon name="leaf" size={48}/>
          <span>知学伴</span>
          <small>ZHIXUEBAN</small>
        </span>
      </div>
    </section>
  </div>
}
